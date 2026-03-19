import logging
import threading
import time
import copy
import json
import os
from pathlib import Path
from typing import Any, List

from fastapi import HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from core.database import SessionLocal
from core.config import settings
from models.user import User
from models.resume import Resume
from models.interview_session import InterviewSession
from models.select_question import SelectQuestion
from models.audio_recording import AudioRecording
from models.question import Question
from models.transcript import Transcript
from models.speech_score_summary import SpeechScoreSummary
from models.speech_score_detail import SpeechScoreDetail
from models.speech_feedback import SpeechFeedback
from models.answer_analysis import AnswerAnalysis

from services.stt_service import run_stt_and_update
from services.speech_score_service import calculate_speech_scores
from services.speech_score_service import upsert_speech_summary, upsert_speech_detail
from services.analysis_service import analyze_answer_by_sel_id
from services.storage_cleanup_service import prune_empty_audio_tree, prune_empty_dirs_upward
from services.interview_cleanup_service import purge_interview_audio_files

# 로거 및 템플릿 설정
logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
DEFAULT_MODEL = settings.OPENAI_MODEL

# 전역 상태 (진행률 및 캐시)
SUBMIT_ANALYSIS_PROGRESS: dict[int, dict[str, object]] = {}
SUBMIT_ANALYSIS_LOCK = threading.Lock()
SUBMIT_ANALYSIS_TIMEOUT_SEC = settings.ANALYSIS_TIMEOUT_SEC
QUESTION_ANALYSIS_PROGRESS: dict[tuple[int, int], dict[str, object]] = {}
QUESTION_ANALYSIS_LOCK = threading.Lock()

WEAKNESS_REPORT_PROGRESS: dict[int, dict[str, object]] = {}
WEAKNESS_REPORT_CACHE: dict[int, dict[str, object]] = {}
WEAKNESS_REPORT_CACHE_LOCK = threading.Lock()
WEAKNESS_REPORT_LOCK = threading.Lock()
WEAKNESS_REPORT_TIMEOUT_SEC = settings.WEAKNESS_REPORT_TIMEOUT_SEC

# 이력서 관련 상수
RUNNING_RESUME_STATUSES = {
    "CLASSIFYING",
    "STRUCTURING",
    "KEYWORDS_EXTRACTING",
    "QUESTION_GENERATING",
}

RESUME_PROGRESS_MAP = {
    "UPLOADED": 5,
    "CLASSIFYING": 20,
    "STRUCTURING": 45,
    "KEYWORDS_EXTRACTING": 65,
    "KEYWORDS_DONE": 80,
    "QUESTION_GENERATING": 90,
    "DONE": 100,
    "FAILED": 100,
}

from core.exceptions import (
    UnauthorizedException,
    ForbiddenException,
    NotFoundException,
    ConflictException,
    BaseAPIException,
)

# --- 공통 헬퍼 함수들 ---

def _get_login_user(request: Request, db: Session) -> User:
    login_user = request.cookies.get("login_user")
    # 미들웨어가 걸러내겠지만, 안전을 위해 남겨둠
    if not login_user:
        raise UnauthorizedException(detail="로그인이 필요한 서비스입니다.")
    user = db.query(User).filter(User.user_username == login_user).first()
    if not user:
        raise UnauthorizedException(detail="유효하지 않은 사용자 정보입니다. 다시 로그인해주세요.")
    return user

def _get_owned_resume(db: Session, user_id: int, resume_id: int) -> Resume:
    resume = db.query(Resume).filter(Resume.resume_id == resume_id).first()
    if not resume:
        raise NotFoundException(detail="요청하신 이력서를 찾을 수 없습니다.")
    if resume.user_id != user_id:
        raise ForbiddenException(detail="해당 이력서에 접근할 권한이 없습니다.")
    return resume

def _get_owned_interview_session(db: Session, user_id: int, session_id: int) -> InterviewSession:
    session = db.query(InterviewSession).filter(InterviewSession.inter_id == session_id).first()
    if not session:
        raise NotFoundException(detail="요청하신 면접 세션을 찾을 수 없습니다.")
    if session.user_id != user_id:
        raise ForbiddenException(detail="해당 면접 세션에 접근할 권한이 없습니다.")
    return session

def _get_interview_session_or_404(db: Session, session_id: int) -> InterviewSession:
    session = db.query(InterviewSession).filter(InterviewSession.inter_id == session_id).first()
    if not session:
        raise NotFoundException(detail="면접 세션을 찾을 수 없습니다.")
    return session

def _has_session_purpose(session: InterviewSession, purpose: str) -> bool:
    return bool(session.question_set and session.question_set.set_purpose == purpose)

def _ensure_session_purpose(session: InterviewSession, purpose: str, detail: str) -> None:
    if not _has_session_purpose(session, purpose):
        raise ConflictException(detail=detail)

def _load_session_question_items(db: Session, session_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(
            SelectQuestion.sel_id.label("sel_id"),
            SelectQuestion.sel_order_no.label("sel_order_no"),
            Question.qust_question_text.label("question_text"),
            AudioRecording.recording_id.label("recording_id"),
            AudioRecording.duration_sec.label("duration_sec"),
        )
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .outerjoin(AudioRecording, AudioRecording.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == session_id)
        .order_by(SelectQuestion.sel_order_no.asc(), SelectQuestion.sel_id.asc())
        .all()
    )
    return [
        {
            "sel_id": row.sel_id,
            "sel_order_no": row.sel_order_no,
            "question_text": row.question_text,
            "is_recorded": row.recording_id is not None,
            "duration_sec": int(row.duration_sec or 0),
        }
        for row in rows
    ]

def _get_session_recording_counts(db: Session, session_id: int) -> tuple[int, int]:
    rows = (
        db.query(AudioRecording.recording_id.label("recording_id"))
        .select_from(SelectQuestion)
        .outerjoin(AudioRecording, AudioRecording.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == session_id)
        .all()
    )
    total_questions = len(rows)
    recorded_questions = sum(1 for row in rows if row.recording_id is not None)
    return total_questions, recorded_questions

def _get_resume_id_by_session(db: Session, session_id: int) -> int | None:
    row = db.query(InterviewSession.resume_id).filter(InterviewSession.inter_id == session_id).first()
    return int(row.resume_id) if row else None

def _get_latest_session_id_by_resume(db: Session, resume_id: int) -> int | None:
    row = (
        db.query(InterviewSession.inter_id)
        .filter(InterviewSession.resume_id == resume_id)
        .order_by(InterviewSession.inter_id.desc())
        .first()
    )
    return int(row.inter_id) if row else None

def _purge_session_audio_files(db: Session, inter_id: int) -> dict[str, int]:
    return purge_interview_audio_files(db=db, inter_id=inter_id)

def _update_submit_progress(inter_id: int, **fields: object) -> None:
    with SUBMIT_ANALYSIS_LOCK:
        base = SUBMIT_ANALYSIS_PROGRESS.get(inter_id, {})
        if base.get("done"): return
        base.update(fields)
        SUBMIT_ANALYSIS_PROGRESS[inter_id] = base

def _question_progress_key(inter_id: int, sel_id: int) -> tuple[int, int]:
    return inter_id, sel_id

def _update_question_analysis_progress(inter_id: int, sel_id: int, **fields: object) -> None:
    key = _question_progress_key(inter_id, sel_id)
    with QUESTION_ANALYSIS_LOCK:
        base = QUESTION_ANALYSIS_PROGRESS.get(key, {})
        if base.get("done") and fields.get("status") == "running":
            base = {}
        base.update(fields)
        QUESTION_ANALYSIS_PROGRESS[key] = base

def _get_question_analysis_progress(inter_id: int, sel_id: int) -> dict[str, object]:
    key = _question_progress_key(inter_id, sel_id)
    with QUESTION_ANALYSIS_LOCK:
        return dict(QUESTION_ANALYSIS_PROGRESS.get(key, {}))

def _wait_for_question_analysis(db: Session, inter_id: int, sel_id: int, timeout_sec: float) -> bool:
    deadline = time.monotonic() + max(0.5, timeout_sec)
    while time.monotonic() < deadline:
        db.expire_all()
        if _is_question_analysis_complete(db=db, sel_id=sel_id):
            return True
        progress = _get_question_analysis_progress(inter_id, sel_id)
        if progress.get("done"):
            return bool(progress.get("ok")) and _is_question_analysis_complete(db=db, sel_id=sel_id)
        time.sleep(0.25)
    return False

def _is_question_analysis_complete(db: Session, sel_id: int) -> bool:
    row = (
        db.query(
            Transcript.transcript_id.label("transcript_id"),
            SpeechScoreSummary.score_id.label("score_id"),
            SpeechScoreDetail.detail_id.label("detail_id"),
            AnswerAnalysis.anal_id.label("anal_id"),
        )
        .select_from(SelectQuestion)
        .outerjoin(Transcript, Transcript.sel_id == SelectQuestion.sel_id)
        .outerjoin(SpeechScoreSummary, SpeechScoreSummary.sel_id == SelectQuestion.sel_id)
        .outerjoin(SpeechScoreDetail, SpeechScoreDetail.sel_id == SelectQuestion.sel_id)
        .outerjoin(AnswerAnalysis, AnswerAnalysis.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.sel_id == sel_id)
        .first()
    )
    if not row:
        return False
    return all(
        (
            row.transcript_id is not None,
            row.score_id is not None,
            row.detail_id is not None,
            row.anal_id is not None,
        )
    )

def _refresh_session_status_if_ready(db: Session, inter_id: int) -> bool:
    rows = (
        db.query(
            SelectQuestion.sel_id.label("sel_id"),
            AudioRecording.recording_id.label("recording_id"),
        )
        .outerjoin(AudioRecording, AudioRecording.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == inter_id)
        .all()
    )
    if not rows or any(row.recording_id is None for row in rows):
        return False
    if any(not _is_question_analysis_complete(db=db, sel_id=int(row.sel_id)) for row in rows):
        return False

    session = db.query(InterviewSession).filter(InterviewSession.inter_id == inter_id).first()
    if not session:
        return False
    session.inter_status = "DONE"
    session.inter_finished_at = func.now()
    db.commit()
    return True

def _update_weakness_report_progress(inter_id: int, **fields: object) -> None:
    with WEAKNESS_REPORT_LOCK:
        base = WEAKNESS_REPORT_PROGRESS.get(inter_id, {})
        if base.get("done"): return
        base.update(fields)
        WEAKNESS_REPORT_PROGRESS[inter_id] = base

def _get_cached_weakness_report(inter_id: int) -> dict[str, object] | None:
    with WEAKNESS_REPORT_CACHE_LOCK:
        cached = WEAKNESS_REPORT_CACHE.get(inter_id)
        return copy.deepcopy(cached) if cached is not None else None

def _set_cached_weakness_report(inter_id: int, report: dict[str, object]) -> None:
    with WEAKNESS_REPORT_CACHE_LOCK:
        WEAKNESS_REPORT_CACHE[inter_id] = copy.deepcopy(report)

def _invalidate_cached_weakness_report(inter_id: int) -> None:
    with WEAKNESS_REPORT_CACHE_LOCK:
        WEAKNESS_REPORT_CACHE.pop(inter_id, None)

def _reset_session_attempt_data(db: Session, inter_id: int) -> dict[str, int]:
    sel_rows = db.query(SelectQuestion.sel_id).filter(SelectQuestion.inter_id == inter_id).all()
    sel_ids = [int(row.sel_id) for row in sel_rows]
    removed_files = 0
    audio_rows = db.query(AudioRecording).filter(AudioRecording.inter_id == inter_id).all()
    for row in audio_rows:
        rel = (row.file_path or "").strip()
        if rel:
            abs_path = Path(settings.STORAGE_DIR) / rel
            try:
                if abs_path.exists():
                    abs_path.unlink()
                    removed_files += 1
            except Exception: pass
            prune_empty_dirs_upward(Path(settings.STORAGE_DIR), rel)
    removed_audio = db.query(AudioRecording).filter(AudioRecording.inter_id == inter_id).delete(synchronize_session=False)
    if sel_ids:
        db.query(Transcript).filter(Transcript.sel_id.in_(sel_ids)).delete(synchronize_session=False)
        db.query(SpeechScoreSummary).filter(SpeechScoreSummary.sel_id.in_(sel_ids)).delete(synchronize_session=False)
        db.query(SpeechScoreDetail).filter(SpeechScoreDetail.sel_id.in_(sel_ids)).delete(synchronize_session=False)
        db.query(SpeechFeedback).filter(SpeechFeedback.sel_id.in_(sel_ids)).delete(synchronize_session=False)
        db.query(AnswerAnalysis).filter(AnswerAnalysis.sel_id.in_(sel_ids)).delete(synchronize_session=False)
        db.query(SelectQuestion).filter(SelectQuestion.inter_id == inter_id).update({SelectQuestion.sel_answer_duration_sec: 0}, synchronize_session=False)
    db.commit()
    prune_empty_audio_tree(Path(settings.STORAGE_DIR))
    return {"removed_audio": int(removed_audio), "removed_files": int(removed_files)}

def _ensure_session_analysis_ready(db: Session, inter_id: int) -> None:
    rows = (
        db.query(SelectQuestion.sel_id, SelectQuestion.sel_order_no, Question.qust_question_text, AudioRecording.file_path, AudioRecording.duration_sec, Transcript.transcript_text)
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .outerjoin(AudioRecording, AudioRecording.sel_id == SelectQuestion.sel_id)
        .outerjoin(Transcript, Transcript.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == inter_id)
        .order_by(SelectQuestion.sel_order_no.asc()).all()
    )
    if not rows: raise NotFoundException(detail="면접 세션 질문을 찾을 수 없습니다.")
    for row in rows:
        if not (row.file_path or "").strip():
            raise ConflictException(detail=f"Q{row.sel_order_no} 질문에 대한 답변 녹음 파일이 누락되었습니다.")
        t_text = (row.transcript_text or "").strip()
        if not t_text:
            _, transcript = run_stt_and_update(db=db, inter_id=inter_id, sel_id=int(row.sel_id))
            t_text = (transcript.transcript_text or "").strip()
        if not t_text: raise ConflictException(detail=f"Q{row.sel_order_no} 질문에 대한 전사 텍스트를 생성하지 못했습니다.")
        score_payload = calculate_speech_scores(transcript_text=t_text, duration_sec=int(row.duration_sec or 0), question_text=row.qust_question_text)
        upsert_speech_summary(db=db, sel_id=int(row.sel_id), score=score_payload)
        upsert_speech_detail(db=db, sel_id=int(row.sel_id), score=score_payload)
        analyze_answer_by_sel_id(db=db, sel_id=int(row.sel_id), model="gpt-4o-mini")
    session = db.query(InterviewSession).filter(InterviewSession.inter_id == inter_id).first()
    if session:
        session.inter_status = "DONE"
        session.inter_finished_at = func.now()
        db.commit()

def _safe_json_list(value):
    if value is None: return []
    if isinstance(value, list): return value
    if isinstance(value, str):
        value = value.strip()
        if not value: return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError: return []
    return []

def _safe_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())

def _score_tone(score: int) -> str:
    if score < 60: return "low"
    if score < 80: return "mid"
    return "high"

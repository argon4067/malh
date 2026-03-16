import time
import threading
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from core.database import get_db, SessionLocal
from models.interview_session import InterviewSession
from models.select_question import SelectQuestion
from models.question import Question
from models.audio_recording import AudioRecording
from models.transcript import Transcript

from services.question_service import generate_weakness_questions_for_session
from services.analysis_service import build_improvement_report, build_improvement_report_detail
from services.stt_service import run_stt_and_update
from services.speech_score_service import calculate_speech_scores, upsert_speech_summary, upsert_speech_detail
from services.analysis_service import analyze_answer_by_sel_id

from web.common import (
    templates, logger, DEFAULT_MODEL, WEAKNESS_REPORT_LOCK, WEAKNESS_REPORT_PROGRESS, WEAKNESS_REPORT_TIMEOUT_SEC,
    _get_login_user, _get_owned_interview_session, _get_interview_session_or_404, _has_session_purpose,
    _ensure_session_purpose, _load_session_question_items, _get_session_recording_counts, _update_weakness_report_progress,
    _get_cached_weakness_report, _set_cached_weakness_report, _invalidate_cached_weakness_report,
    _purge_session_audio_files, _ensure_session_analysis_ready
)

router = APIRouter()

def _run_weakness_report_job(inter_id: int) -> None:
    db = SessionLocal()
    try:
        job_started = time.monotonic()
        rows = (
            db.query(SelectQuestion.sel_id, SelectQuestion.sel_order_no, Question.qust_question_text, AudioRecording.file_path, AudioRecording.duration_sec, Transcript.transcript_text)
            .join(Question).outerjoin(AudioRecording).outerjoin(Transcript)
            .filter(SelectQuestion.inter_id == inter_id).order_by(SelectQuestion.sel_order_no.asc()).all()
        )
        total = len(rows)
        if total == 0:
            _update_weakness_report_progress(inter_id, status="failed", done=True, message="질문을 찾을 수 없습니다.")
            return
        _update_weakness_report_progress(inter_id, status="running", total=total, completed=0, message="리포트 준비 시작...")
        processed, failed = [], []
        for index, row in enumerate(rows, start=1):
            if time.monotonic() - job_started > WEAKNESS_REPORT_TIMEOUT_SEC: break
            sel_id, sel_order_no = int(row.sel_id), int(row.sel_order_no)
            _update_weakness_report_progress(inter_id, current_index=index, message=f"보강 Q{sel_order_no} 분석 중...")
            if not (row.file_path or "").strip():
                failed.append({"sel_id": sel_id, "reason": "녹음 없음"}); continue
            t_text = (row.transcript_text or "").strip()
            if not t_text:
                try:
                    _, transcript = run_stt_and_update(db, inter_id, sel_id)
                    t_text = transcript.transcript_text
                except Exception as e:
                    failed.append({"sel_id": sel_id, "reason": str(e)}); continue
            try:
                score_payload = calculate_speech_scores(t_text, int(row.duration_sec or 0), row.qust_question_text)
                upsert_speech_summary(db, sel_id, score_payload); upsert_speech_detail(db, sel_id, score_payload)
                analyze_answer_by_sel_id(db, sel_id, model="gpt-4o-mini")
                processed.append({"sel_id": sel_id}); _update_weakness_report_progress(inter_id, completed=index, message=f"Q{sel_order_no} 완료")
            except Exception as e:
                db.rollback(); failed.append({"sel_id": sel_id, "reason": str(e)})
        if not failed:
            report = build_improvement_report(db, inter_id); _set_cached_weakness_report(inter_id, report)
        _update_weakness_report_progress(inter_id, status="done", done=True, ok=len(failed) == 0, message="리포트 준비 완료" if not failed else "일부 실패", finished_at=int(time.time()))
    except Exception as e:
        db.rollback(); _update_weakness_report_progress(inter_id, status="failed", done=True, message=f"작업 실패: {e}")
    finally: db.close()

@router.get("/interviews/{session_id}/weakness")
async def weakness_questions(request: Request, session_id: int, db: Session = Depends(get_db)):
    session = _get_interview_session_or_404(db, session_id)
    if not _has_session_purpose(session, "WEAKNESS"):
        return RedirectResponse(url=f"/interviews/{session_id}/weakness/wait", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    return templates.TemplateResponse("weakness/questions.html", {"request": request, "session_id": session_id, "weakness_items": _load_session_question_items(db, session_id)})

@router.get("/interviews/{session_id}/weakness/wait")
async def weakness_wait(request: Request, session_id: int, db: Session = Depends(get_db)):
    session = _get_interview_session_or_404(db, session_id)
    if _has_session_purpose(session, "WEAKNESS"):
        return RedirectResponse(url=f"/interviews/{session_id}/weakness", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    return templates.TemplateResponse("weakness/wait.html", {"request": request, "session_id": session_id})

@router.post("/interviews/{session_id}/weakness/start")
async def start_weakness_question_generation(request: Request, session_id: int, db: Session = Depends(get_db)):
    user = _get_login_user(request, db)
    source = _get_owned_interview_session(db, user.user_id, session_id)
    _ensure_session_purpose(source, "DEFAULT", "기본 면접 결과에서만 생성 가능합니다.")
    if source.inter_status != "DONE": raise HTTPException(status_code=409, detail="분석 완료 후 시도해 주세요.")
    result = generate_weakness_questions_for_session(db, session_id, DEFAULT_MODEL)
    _purge_session_audio_files(db, session_id)
    return {"ok": True, **result}

@router.get("/interviews/{session_id}/weakness/report-loading")
async def weakness_report_loading(request: Request, session_id: int, db: Session = Depends(get_db)):
    session = _get_interview_session_or_404(db, session_id)
    _ensure_session_purpose(session, "WEAKNESS", "약점 보강 세션이 아닙니다.")
    return templates.TemplateResponse("weakness/report_loading.html", {"request": request, "session_id": session_id})

@router.post("/interviews/{inter_id}/weakness/report/start")
async def start_weakness_report_job(inter_id: int, db: Session = Depends(get_db)):
    session = _get_interview_session_or_404(db, inter_id)
    _ensure_session_purpose(session, "WEAKNESS", "약점 보강 세션이 아닙니다.")
    total, recorded = _get_session_recording_counts(db, inter_id)
    if total == 0 or recorded < total: raise HTTPException(status_code=400, detail="모든 녹음을 완료해 주세요.")
    _invalidate_cached_weakness_report(inter_id)
    with WEAKNESS_REPORT_LOCK:
        if WEAKNESS_REPORT_PROGRESS.get(inter_id, {}).get("status") == "running": return {"ok": True, "status": "running"}
        WEAKNESS_REPORT_PROGRESS[inter_id] = {"status": "running", "done": False, "ok": False, "started_at": int(time.time())}
    threading.Thread(target=_run_weakness_report_job, args=(inter_id,), daemon=True).start()
    return {"ok": True, "inter_id": inter_id, "status": "started"}

@router.get("/interviews/{inter_id}/weakness/report/progress")
async def get_weakness_report_progress(inter_id: int):
    with WEAKNESS_REPORT_LOCK:
        progress = dict(WEAKNESS_REPORT_PROGRESS.get(inter_id, {}))
        if progress.get("status") == "running" and (int(time.time()) - int(progress.get("started_at", 0))) > WEAKNESS_REPORT_TIMEOUT_SEC:
            progress.update({"status": "failed", "done": True, "message": "시간 초과"}); WEAKNESS_REPORT_PROGRESS[inter_id] = progress
    if not progress: raise HTTPException(status_code=404, detail="Job not found")
    total, completed = int(progress.get("total", 0)), int(progress.get("completed", 0))
    progress["percent"] = int((completed / total) * 100) if total > 0 else 0
    return progress

@router.get("/interviews/{session_id}/weakness/report")
async def weakness_report(request: Request, session_id: int, db: Session = Depends(get_db)):
    session = _get_interview_session_or_404(db, session_id)
    _ensure_session_purpose(session, "WEAKNESS", "약점 보강 세션이 아닙니다.")
    cached = _get_cached_weakness_report(session_id)
    if cached is not None: return templates.TemplateResponse("weakness/report.html", {"request": request, "session_id": session_id, "report": cached})
    _ensure_session_analysis_ready(db, session_id)
    report = build_improvement_report(db, session_id); _set_cached_weakness_report(session_id, report)
    return templates.TemplateResponse("weakness/report.html", {"request": request, "session_id": session_id, "report": report})

@router.get("/interviews/{session_id}/weakness/report/{question_id}")
async def weakness_report_detail(request: Request, session_id: int, question_id: int, db: Session = Depends(get_db)):
    session = _get_interview_session_or_404(db, session_id)
    _ensure_session_purpose(session, "WEAKNESS", "약점 보강 세션이 아닙니다.")
    if _get_cached_weakness_report(session_id) is None: raise HTTPException(status_code=409, detail="리포트 미준비")
    return templates.TemplateResponse("weakness/report_detail.html", {"request": request, "session_id": session_id, "detail": build_improvement_report_detail(db, session_id, question_id)["detail"]})

@router.post("/interviews/{session_id}/weakness/report/home")
async def weakness_report_go_home(request: Request, session_id: int, db: Session = Depends(get_db)):
    user = _get_login_user(request, db)
    session = _get_owned_interview_session(db, user.user_id, session_id)
    _ensure_session_purpose(session, "WEAKNESS", "약점 보강 세션이 아닙니다.")
    _purge_session_audio_files(db, session_id); _invalidate_cached_weakness_report(session_id)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/interviews/{session_id}/weakness/{question_id}")
async def weakness_detail(request: Request, session_id: int, question_id: int, db: Session = Depends(get_db)):
    row = db.query(SelectQuestion.sel_id, SelectQuestion.sel_order_no, Question.qust_question_text.label("question_text")).join(Question).filter(SelectQuestion.inter_id == session_id, SelectQuestion.sel_id == question_id).first()
    if not row: raise HTTPException(status_code=404, detail="질문 없음")
    return templates.TemplateResponse("weakness/question_detail.html", {"request": request, "session_id": session_id, "question_id": question_id, "weakness_item": {"sel_id": row.sel_id, "sel_order_no": row.sel_order_no, "question_text": row.question_text}})

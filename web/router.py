from pathlib import Path
import threading
import time
import logging
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
    BackgroundTasks,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.database import SessionLocal, get_db
from models.user import User
from models.audio_recording import AudioRecording
from models.interview_session import InterviewSession
from models.question import Question
from models.resume import Resume
from models.select_question import SelectQuestion
from models.transcript import Transcript
from models.transcript_refine import TranscriptRefine
from fastapi.responses import RedirectResponse

from services.resume_service import (
    DEFAULT_MODEL,
    analyze_saved_resume,
    create_resume_record,
    delete_resume,
    get_resume_analysis_result,
    update_resume_status,
)

from models.question_set import QuestionSet
from models.question_filter_result import QuestionFilterResult
from services.question_service import ensure_questions_generated_for_resume
from services.question_service import generate_questions_for_resume
from services.question_service import get_latest_completed_question_set
from services.speech_score_service import (
    calculate_speech_scores,
    get_speech_detail_payload,
    upsert_speech_detail,
    upsert_speech_summary,
)
from services.speech_feedback_service import (
    generate_speech_feedback,
    get_speech_feedback,
    upsert_speech_feedback,
)

from sqlalchemy.sql import func

from services.stt_service import (
    build_recording_paths,
    resolve_recording_extension,
    run_stt_and_update,
    save_recording_and_upsert,
)
from services.transcript_refine_service import (
    refine_transcript_with_guardrails,
    upsert_refine_result,
)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

web_router = APIRouter()
SUBMIT_ANALYSIS_PROGRESS: dict[int, dict[str, object]] = {}
SUBMIT_ANALYSIS_LOCK = threading.Lock()

logger = logging.getLogger(__name__)

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

def _get_login_user(request: Request, db: Session) -> User:
    login_user = request.cookies.get("login_user")
    if not login_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    user = (
        db.query(User)
        .filter(User.user_username == login_user)
        .first()
    )
    if not user:
        raise HTTPException(status_code=401, detail="유효하지 않은 로그인 정보입니다.")

    return user


def _get_owned_resume(db: Session, user_id: int, resume_id: int) -> Resume:
    resume = (
        db.query(Resume)
        .filter(Resume.resume_id == resume_id, Resume.user_id == user_id)
        .first()
    )
    if not resume:
        raise HTTPException(status_code=404, detail="이력서를 찾을 수 없습니다.")
    return resume


def _get_resume_id_by_session(db: Session, session_id: int) -> int | None:
    row = (
        db.query(InterviewSession.resume_id)
        .filter(InterviewSession.inter_id == session_id)
        .first()
    )
    return int(row.resume_id) if row else None


def _get_latest_session_id_by_resume(db: Session, resume_id: int) -> int | None:
    row = (
        db.query(InterviewSession.inter_id)
        .filter(InterviewSession.resume_id == resume_id)
        .order_by(InterviewSession.inter_id.desc())
        .first()
    )
    return int(row.inter_id) if row else None


def _update_submit_progress(inter_id: int, **fields: object) -> None:
    with SUBMIT_ANALYSIS_LOCK:
        base = SUBMIT_ANALYSIS_PROGRESS.get(inter_id, {})
        base.update(fields)
        SUBMIT_ANALYSIS_PROGRESS[inter_id] = base


def _run_submit_analysis_job(inter_id: int) -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(
                SelectQuestion.sel_id.label("sel_id"),
                SelectQuestion.sel_order_no.label("sel_order_no"),
                Question.qust_question_text.label("question_text"),
                AudioRecording.file_path.label("file_path"),
                AudioRecording.duration_sec.label("duration_sec"),
                Transcript.transcript_text.label("transcript_text"),
            )
            .join(Question, Question.qust_id == SelectQuestion.qust_id)
            .outerjoin(AudioRecording, AudioRecording.sel_id == SelectQuestion.sel_id)
            .outerjoin(Transcript, Transcript.sel_id == SelectQuestion.sel_id)
            .filter(SelectQuestion.inter_id == inter_id)
            .order_by(SelectQuestion.sel_order_no.asc(), SelectQuestion.sel_id.asc())
            .all()
        )

        total = len(rows)
        if total == 0:
            _update_submit_progress(
                inter_id,
                status="failed",
                done=True,
                ok=False,
                total=0,
                completed=0,
                failed_count=0,
                message="면접 세션 질문을 찾을 수 없습니다.",
            )
            return

        _update_submit_progress(
            inter_id,
            status="running",
            total=total,
            completed=0,
            failed_count=0,
            message="분석을 시작합니다.",
            done=False,
            ok=False,
        )

        processed: list[dict[str, int | str]] = []
        failed: list[dict[str, int | str]] = []

        for index, row in enumerate(rows, start=1):
            sel_id = int(row.sel_id)
            sel_order_no = int(row.sel_order_no)
            _update_submit_progress(
                inter_id,
                current_index=index,
                current_sel_id=sel_id,
                current_sel_order_no=sel_order_no,
                message=f"Q{sel_order_no} 분석 중...",
            )

            if not (row.file_path or "").strip():
                failed.append(
                    {
                        "sel_id": sel_id,
                        "sel_order_no": sel_order_no,
                        "reason": "녹음 파일이 없습니다.",
                    }
                )
                _update_submit_progress(
                    inter_id,
                    completed=index,
                    failed_count=len(failed),
                    message=f"Q{sel_order_no} 녹음 없음",
                )
                continue

            transcript_text = (row.transcript_text or "").strip()
            if not transcript_text:
                _update_submit_progress(inter_id, message=f"Q{sel_order_no} STT 처리 중...")
                try:
                    _, transcript = run_stt_and_update(db=db, inter_id=inter_id, sel_id=sel_id)
                    transcript_text = (transcript.transcript_text or "").strip()
                except Exception as exc:
                    failed.append(
                        {
                            "sel_id": sel_id,
                            "sel_order_no": sel_order_no,
                            "reason": str(exc),
                        }
                    )
                    _update_submit_progress(
                        inter_id,
                        completed=index,
                        failed_count=len(failed),
                        message=f"Q{sel_order_no} STT 실패",
                    )
                    continue

            if not transcript_text:
                failed.append(
                    {
                        "sel_id": sel_id,
                        "sel_order_no": sel_order_no,
                        "reason": "전사 텍스트가 비어 있습니다.",
                    }
                )
                _update_submit_progress(
                    inter_id,
                    completed=index,
                    failed_count=len(failed),
                    message=f"Q{sel_order_no} 텍스트 없음",
                )
                continue

            _update_submit_progress(inter_id, message=f"Q{sel_order_no} 발화 지표 계산 중...")
            score_payload = calculate_speech_scores(
                transcript_text=transcript_text,
                duration_sec=int(row.duration_sec or 0),
                question_text=row.question_text,
            )
            upsert_speech_summary(db=db, sel_id=sel_id, score=score_payload)
            upsert_speech_detail(db=db, sel_id=sel_id, score=score_payload)
            processed.append({"sel_id": sel_id, "sel_order_no": sel_order_no})

            _update_submit_progress(
                inter_id,
                completed=index,
                failed_count=len(failed),
                message=f"Q{sel_order_no} 완료",
            )

        session = db.query(InterviewSession).filter(InterviewSession.inter_id == inter_id).first()
        if session and not failed:
            session.inter_status = "DONE"
            session.inter_finished_at = func.now()
            db.commit()

        _update_submit_progress(
            inter_id,
            status="done",
            done=True,
            ok=len(failed) == 0,
            processed_count=len(processed),
            failed_count=len(failed),
            processed=processed,
            failed=failed,
            message="분석이 완료되었습니다." if not failed else "일부 질문 분석에 실패했습니다.",
            finished_at=int(time.time()),
        )
    except Exception as exc:
        _update_submit_progress(
            inter_id,
            status="failed",
            done=True,
            ok=False,
            message=f"분석 작업 실패: {exc}",
            finished_at=int(time.time()),
        )
    finally:
        db.close()

def _run_resume_pipeline_background(resume_id: int, model: str) -> None:
    db_gen = get_db()
    db = next(db_gen)

    try:
        logger.info("RESUME_PIPELINE_START resume_id=%s model=%s", resume_id, model)

        analyze_saved_resume(
            db=db,
            resume_id=resume_id,
            model=model,
        )

        resume = (
            db.query(Resume)
            .filter(Resume.resume_id == resume_id)
            .first()
        )
        if not resume:
            return

        update_resume_status(db, resume, "QUESTION_GENERATING")

        ensure_questions_generated_for_resume(
            db=db,
            resume_id=resume_id,
            target_count=30,
            purpose="DEFAULT",
            model=model,
        )

        resume = (
            db.query(Resume)
            .filter(Resume.resume_id == resume_id)
            .first()
        )
        if resume:
            update_resume_status(db, resume, "DONE")

        logger.info("RESUME_PIPELINE_DONE resume_id=%s", resume_id)

    except Exception as e:
        db.rollback()

        logger.exception("RESUME_PIPELINE_FAIL resume_id=%s err=%s", resume_id, e)

        resume = (
            db.query(Resume)
            .filter(Resume.resume_id == resume_id)
            .first()
        )
        if resume:
            try:
                update_resume_status(db, resume, "FAILED", str(e))
            except Exception:
                db.rollback()

    finally:
        try:
            db_gen.close()
        except Exception:
            pass


@web_router.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# Auth
@web_router.get("/auth/login")
async def login(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})


@web_router.get("/auth/agree")
async def agree(request: Request):
    return templates.TemplateResponse("auth/agree.html", {"request": request})


@web_router.get("/auth/signup")
async def signup(request: Request):
    return templates.TemplateResponse("auth/signup.html", {"request": request})


# Resume
@web_router.get("/resumes")
async def resume_list(
    request: Request,
    db: Session = Depends(get_db),
):
    user = _get_login_user(request, db)

    resumes = (
        db.query(Resume)
        .filter(Resume.user_id == user.user_id)
        .order_by(Resume.resume_id.desc())
        .all()
    )

    return templates.TemplateResponse(
        "resume/list.html",
        {
            "request": request,
            "resume_id": None,
            "default_model": DEFAULT_MODEL,
            "resumes": resumes,
        },
    )


@web_router.post("/resumes")
async def create_resume(
    request: Request,
    model: str = Form(DEFAULT_MODEL),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    login_user = request.cookies.get("login_user")
    if not login_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    user = (
        db.query(User)
        .filter(User.user_username == login_user)
        .first()
    )
    if not user:
        raise HTTPException(status_code=401, detail="유효하지 않은 로그인 정보입니다.")

    try:
        data = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"파일 읽기 실패: {e}") from e

    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    resume = create_resume_record(
        db=db,
        user_id=user.user_id,
        original_filename=file.filename or "resume.pdf",
        data=data,
    )

    return {
        "resume_id": resume.resume_id,
        "model": model,
    }


@web_router.get("/resumes/{resume_id}/wait")
async def resume_wait(
    request: Request,
    resume_id: int,
    model: str = DEFAULT_MODEL,
):
    return templates.TemplateResponse(
        "resume/wait.html",
        {
            "request": request,
            "resume_id": resume_id,
            "model": model,
        },
    )


@web_router.get("/resumes/{resume_id}")
async def resume_detail(
    request: Request,
    resume_id: int,
    db: Session = Depends(get_db),
):
    user = _get_login_user(request, db)
    _get_owned_resume(db, user.user_id, resume_id)

    result = get_resume_analysis_result(db, resume_id)

    return templates.TemplateResponse(
        "resume/detail.html",
        {
            "request": request,
            "resume_id": resume_id,
            "resume": result["resume"],
            "classification": result["classification"],
            "keywords": result["keywords"],
            "structured": result["structured"],
            "practice_history": [],
            "weaknesses": [],
            "score_history": [],
        }
    )


@web_router.get("/resumes/{resume_id}/feedback")
async def resume_feedback(
    request: Request,
    resume_id: int,
    db: Session = Depends(get_db),
):
    user = _get_login_user(request, db)
    _get_owned_resume(db, user.user_id, resume_id)

    return templates.TemplateResponse(
        "resume/feedback.html",
        {
            "request": request,
            "resume_id": resume_id,
            "session_id": _get_latest_session_id_by_resume(db, resume_id),
        },
    )

@web_router.post("/resumes/{resume_id}/analyze")
@web_router.post("/resumes/{resume_id}/analyze/start")
async def start_resume_analysis(
    request: Request,
    resume_id: int,
    background_tasks: BackgroundTasks,
    model: str = Form(DEFAULT_MODEL),
    db: Session = Depends(get_db),
):
    user = _get_login_user(request, db)
    resume = _get_owned_resume(db, user.user_id, resume_id)

    # 이미 완료된 경우
    if resume.resume_status == "DONE":
        return {
            "ok": True,
            "resume_id": resume_id,
            "status": resume.resume_status,
            "message": "이미 분석 완료된 이력서입니다.",
        }

    # 이미 진행 중인 경우
    if resume.resume_status in RUNNING_RESUME_STATUSES:
        return {
            "ok": True,
            "resume_id": resume_id,
            "status": resume.resume_status,
            "message": "이미 분석이 진행 중입니다.",
        }

    # 시작 상태로 변경
    update_resume_status(db, resume, "CLASSIFYING")

    # 백그라운드 실행
    background_tasks.add_task(_run_resume_pipeline_background, resume_id, model)

    return {
        "ok": True,
        "resume_id": resume_id,
        "status": "CLASSIFYING",
        "message": "분석이 시작되었습니다.",
    }

@web_router.post("/resumes/{resume_id}/delete")
async def remove_resume(
    request: Request,
    resume_id: int,
    db: Session = Depends(get_db),
):
    user = _get_login_user(request, db)
    _get_owned_resume(db, user.user_id, resume_id)

    delete_resume(db=db, resume_id=resume_id)
    return RedirectResponse(url="/resumes", status_code=status.HTTP_303_SEE_OTHER)

@web_router.get("/resumes/{resume_id}/status")
async def get_resume_status(
    request: Request,
    resume_id: int,
    db: Session = Depends(get_db),
):
    user = _get_login_user(request, db)
    resume = _get_owned_resume(db, user.user_id, resume_id)

    return {
        "resume_id": resume.resume_id,
        "status": resume.resume_status,
        "progress": RESUME_PROGRESS_MAP.get(resume.resume_status, 0),
        "error_message": resume.resume_error_message,
        "detail_url": f"/resumes/{resume.resume_id}",
    }

# question
@web_router.post("/questions/generate/{resume_id}")
async def generate_questions(
    request: Request,
    resume_id: int,
    db: Session = Depends(get_db),
):
    user = _get_login_user(request, db)
    _get_owned_resume(db, user.user_id, resume_id)

    try:
        question_set = generate_questions_for_resume(
            db=db,
            resume_id=resume_id,
            target_count=30,
            purpose="DEFAULT",
        )

        selected_questions = (
            db.query(Question)
            .filter(
                Question.set_id == question_set.set_id,
                Question.qust_is_selected == 1,
            )
            .order_by(Question.qust_id.asc())
            .all()
        )

        return {
            "message": "질문 생성이 완료되었습니다.",
            "set_id": question_set.set_id,
            "set_status": question_set.set_status,
            "set_attempt": question_set.set_attempt,
            "selected_count": len(selected_questions),
            "questions": [
                {
                    "qust_id": q.qust_id,
                    "category": q.qust_category,
                    "difficulty": q.qust_difficulty,
                    "question_text": q.qust_question_text,
                    "evidence": q.qust_evidence,
                }
                for q in selected_questions
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"질문 생성 실패: {e}") from e


@web_router.get("/questions/set/{set_id}")
async def get_question_set_result(
    request: Request,
    set_id: int,
    db: Session = Depends(get_db),
):
    user = _get_login_user(request, db)

    question_set = (
        db.query(QuestionSet)
        .filter(QuestionSet.set_id == set_id)
        .first()
    )
    if not question_set:
        raise HTTPException(status_code=404, detail="질문 세트를 찾을 수 없습니다.")

    _get_owned_resume(db, user.user_id, question_set.resume_id)

    selected_questions = (
        db.query(Question)
        .filter(
            Question.set_id == set_id,
            Question.qust_is_selected == 1,
        )
        .order_by(Question.qust_id.asc())
        .all()
    )

    rejected_questions = (
        db.query(Question, QuestionFilterResult)
        .join(
            QuestionFilterResult,
            Question.qust_id == QuestionFilterResult.qust_id,
        )
        .filter(
            Question.set_id == set_id,
            Question.qust_is_selected == 0,
        )
        .order_by(Question.qust_id.asc())
        .all()
    )

    return {
        "set_id": question_set.set_id,
        "resume_id": question_set.resume_id,
        "set_status": question_set.set_status,
        "set_attempt": question_set.set_attempt,
        "set_purpose": question_set.set_purpose,
        "selected_count": len(selected_questions),
        "rejected_count": len(rejected_questions),
        "selected_questions": [
            {
                "qust_id": q.qust_id,
                "category": q.qust_category,
                "difficulty": q.qust_difficulty,
                "question_text": q.qust_question_text,
                "evidence": q.qust_evidence,
            }
            for q in selected_questions
        ],
        "rejected_questions": [
            {
                "qust_id": q.qust_id,
                "category": q.qust_category,
                "difficulty": q.qust_difficulty,
                "question_text": q.qust_question_text,
                "evidence": q.qust_evidence,
                "reasons": f.qfr_reasons,
                "duplicate_similarity": float(f.qfr_duplicate_similarity)
                if f.qfr_duplicate_similarity is not None
                else None,
            }
            for q, f in rejected_questions
        ],
    }

#
@web_router.post("/resumes/{resume_id}/start-practice")
async def start_practice(
    request: Request,
    resume_id: int,
    db: Session = Depends(get_db),
):
    user = _get_login_user(request, db)
    _get_owned_resume(db, user.user_id, resume_id)

    question_set = get_latest_completed_question_set(db, resume_id)
    if not question_set:
        raise HTTPException(
            status_code=409,
            detail="생성된 질문 세트가 없습니다. 먼저 이력서 분석을 완료해주세요.",
        )

    selected_questions = (
        db.query(Question)
        .filter(
            Question.set_id == question_set.set_id,
            Question.qust_is_selected == 1,
        )
        .order_by(func.rand())
        .limit(5)
        .all()
    )

    if len(selected_questions) < 5:
        raise HTTPException(
            status_code=409,
            detail="출제 가능한 질문이 5개 미만입니다.",
        )

    try:
        interview_session = InterviewSession(
            user_id=user.user_id,
            resume_id=resume_id,
            set_id=question_set.set_id,
            inter_status="IN_PROGRESS",
        )
        db.add(interview_session)
        db.flush()

        for idx, question in enumerate(selected_questions, start=1):
            db.add(
                SelectQuestion(
                    inter_id=interview_session.inter_id,
                    qust_id=question.qust_id,
                    sel_order_no=idx,
                )
            )

        db.commit()
        db.refresh(interview_session)

        return {
            "ok": True,
            "session_id": interview_session.inter_id,
            "resume_id": resume_id,
            "set_id": question_set.set_id,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"연습 세션 생성 실패: {e}",
        ) from e


# Interview
@web_router.get("/interviews/{session_id}/wait")
async def interview_wait(
    request: Request,
    session_id: int,
):
    return templates.TemplateResponse(
        "interview/wait.html",
        {
            "request": request,
            "session_id": session_id,
        },
    )


@web_router.get("/interviews/{session_id}")
async def interview_questions(
    request: Request,
    session_id: int,
    db: Session = Depends(get_db),
):
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

    question_items = [
        {
            "sel_id": row.sel_id,
            "sel_order_no": row.sel_order_no,
            "question_text": row.question_text,
            "is_recorded": row.recording_id is not None,
            "duration_sec": int(row.duration_sec or 0),
        }
        for row in rows
    ]
    total_questions = len(question_items)
    recorded_questions = sum(1 for item in question_items if item["is_recorded"])

    return templates.TemplateResponse(
        "interview/questions.html",
        {
            "request": request,
            "session_id": session_id,
            "resume_id": _get_resume_id_by_session(db, session_id),
            "question_items": question_items,
            "total_questions": total_questions,
            "recorded_questions": recorded_questions,
        },
    )


@web_router.get("/interviews/{session_id}/submit-loading")
async def interview_submit_loading(
    request: Request,
    session_id: int,
):
    return templates.TemplateResponse(
        "interview/submit_loading.html",
        {
            "request": request,
            "session_id": session_id,
        },
    )


@web_router.get("/interviews/{session_id}/questions/{question_id}")
async def interview_question_detail(
    request: Request,
    session_id: int,
    question_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(
            SelectQuestion.sel_id.label("sel_id"),
            SelectQuestion.sel_order_no.label("sel_order_no"),
            Question.qust_question_text.label("question_text"),
        )
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .filter(
            SelectQuestion.inter_id == session_id,
            SelectQuestion.sel_id == question_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="세션에서 해당 질문을 찾을 수 없습니다.",
        )

    return templates.TemplateResponse(
        "interview/question_detail.html",
        {
            "request": request,
            "session_id": session_id,
            "question_id": question_id,
            "question_item": {
                "sel_id": row.sel_id,
                "sel_order_no": row.sel_order_no,
                "question_text": row.question_text,
            },
        },
    )


# Result
@web_router.get("/interviews/{session_id}/results")
async def result_index(
    request: Request,
    session_id: int,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            SelectQuestion.sel_id.label("sel_id"),
            SelectQuestion.sel_order_no.label("sel_order_no"),
            SelectQuestion.sel_answer_duration_sec.label("sel_duration_sec"),
            Question.qust_question_text.label("question_text"),
            AudioRecording.duration_sec.label("recorded_duration_sec"),
            AudioRecording.recording_id.label("recording_id"),
        )
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .outerjoin(AudioRecording, AudioRecording.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == session_id)
        .order_by(SelectQuestion.sel_order_no.asc(), SelectQuestion.sel_id.asc())
        .all()
    )

    result_items = [
        {
            "sel_id": row.sel_id,
            "sel_order_no": row.sel_order_no,
            "question_text": row.question_text,
            "duration_sec": int(
                row.recorded_duration_sec
                if row.recorded_duration_sec is not None
                else (row.sel_duration_sec or 0)
            ),
            "is_recorded": row.recording_id is not None,
        }
        for row in rows
    ]

    return templates.TemplateResponse(
        "result/index.html",
        {
            "request": request,
            "session_id": session_id,
            "resume_id": _get_resume_id_by_session(db, session_id),
            "result_items": result_items,
        },
    )


@web_router.get("/interviews/{session_id}/results/{sel_id}/analysis")
async def result_analysis(request: Request, session_id: int, sel_id: int):
    return RedirectResponse(
        url=f"/interviews/{session_id}/results/{sel_id}/stt",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@web_router.get("/interviews/{session_id}/results/{sel_id}/stt")
async def result_analysis_stt(
    request: Request,
    session_id: int,
    sel_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(
            SelectQuestion.sel_id.label("sel_id"),
            Question.qust_question_text.label("question_text"),
        )
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .filter(SelectQuestion.inter_id == session_id, SelectQuestion.sel_id == sel_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="세션에서 해당 질문을 찾을 수 없습니다.",
        )

    score_payload = get_speech_detail_payload(db=db, sel_id=sel_id)
    feedback_row = get_speech_feedback(db=db, sel_id=sel_id)
    feedback_payload = None
    if feedback_row:
        feedback_payload = {
            "report_md": feedback_row.sfb_report_md,
            "coaching_md": feedback_row.sfb_coaching_md,
            "model": feedback_row.sfb_model,
        }

    return templates.TemplateResponse(
        "result/analysis_stt.html",
        {
            "request": request,
            "session_id": session_id,
            "sel_id": sel_id,
            "question_text": row.question_text,
            "score": score_payload,
            "feedback": feedback_payload,
        },
    )


@web_router.get("/interviews/{session_id}/results/{sel_id}/text")
async def result_transcript(
    request: Request,
    session_id: int,
    sel_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(
            SelectQuestion.sel_id.label("sel_id"),
            SelectQuestion.sel_order_no.label("sel_order_no"),
            Question.qust_question_text.label("question_text"),
            AudioRecording.duration_sec.label("duration_sec"),
            AudioRecording.file_path.label("file_path"),
            Transcript.transcript_text.label("transcript_text"),
            TranscriptRefine.r_refined_text.label("refined_text"),
            TranscriptRefine.r_status.label("refine_status"),
        )
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .outerjoin(AudioRecording, AudioRecording.sel_id == SelectQuestion.sel_id)
        .outerjoin(Transcript, Transcript.sel_id == SelectQuestion.sel_id)
        .outerjoin(TranscriptRefine, TranscriptRefine.transcript_id == Transcript.transcript_id)
        .filter(SelectQuestion.inter_id == session_id, SelectQuestion.sel_id == sel_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript in session not found.",
        )

    transcript_text = (row.transcript_text or "").strip()
    if not transcript_text and (row.file_path or "").strip():
        try:
            _, transcript = run_stt_and_update(db=db, inter_id=session_id, sel_id=sel_id)
            transcript_text = (transcript.transcript_text or "").strip()
        except Exception:
            transcript_text = ""

    effective_text = transcript_text or "전사 텍스트가 아직 생성되지 않았습니다."
    if row.refine_status == "APPLIED" and (row.refined_text or "").strip():
        effective_text = row.refined_text
    audio_url = f"/storage/{row.file_path}" if (row.file_path or "").strip() else None

    return templates.TemplateResponse(
        "result/transcript.html",
        {
            "request": request,
            "session_id": session_id,
            "sel_id": sel_id,
            "transcript_item": {
                "sel_order_no": row.sel_order_no,
                "question_text": row.question_text,
                "duration_sec": int(row.duration_sec or 0),
                "transcript_text": effective_text,
                "audio_url": audio_url,
            },
        },
    )


# Weakness
@web_router.get("/interviews/{session_id}/weakness")
async def weakness_questions(
    request: Request,
    session_id: int,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            SelectQuestion.sel_id.label("sel_id"),
            SelectQuestion.sel_order_no.label("sel_order_no"),
            Question.qust_question_text.label("question_text"),
        )
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .filter(SelectQuestion.inter_id == session_id)
        .order_by(SelectQuestion.sel_order_no.asc(), SelectQuestion.sel_id.asc())
        .all()
    )

    weakness_items = [
        {
            "sel_id": row.sel_id,
            "sel_order_no": row.sel_order_no,
            "question_text": row.question_text,
        }
        for row in rows
    ]

    return templates.TemplateResponse(
        "weakness/questions.html",
        {"request": request, "session_id": session_id, "weakness_items": weakness_items},
    )


@web_router.get("/interviews/{session_id}/weakness/wait")
async def weakness_wait(request: Request, session_id: int):
    return templates.TemplateResponse(
        "weakness/wait.html",
        {"request": request, "session_id": session_id},
    )


@web_router.get("/interviews/{session_id}/weakness/{question_id}")
async def weakness_detail(
    request: Request,
    session_id: int,
    question_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(
            SelectQuestion.sel_id.label("sel_id"),
            SelectQuestion.sel_order_no.label("sel_order_no"),
            Question.qust_question_text.label("question_text"),
        )
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .filter(
            SelectQuestion.inter_id == session_id,
            SelectQuestion.sel_id == question_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="세션에서 해당 약점 질문을 찾을 수 없습니다.",
        )

    return templates.TemplateResponse(
        "weakness/question_detail.html",
        {
            "request": request,
            "session_id": session_id,
            "question_id": question_id,
            "weakness_item": {
                "sel_id": row.sel_id,
                "sel_order_no": row.sel_order_no,
                "question_text": row.question_text,
            },
        },
    )


# Account
@web_router.get("/account/password")
async def account_password(request: Request):
    return templates.TemplateResponse("account/password.html", {"request": request})


@web_router.get("/account/withdraw")
async def account_withdraw(request: Request):
    return templates.TemplateResponse("account/withdraw.html", {"request": request})


@web_router.post(
    "/api/interviews/{inter_id}/questions/{sel_id}/recordings",
    status_code=status.HTTP_201_CREATED,
)
async def upload_recording(
    inter_id: int,
    sel_id: int,
    audio_file: UploadFile = File(...),
    duration_sec: int | None = Form(default=None),
    db: Session = Depends(get_db),
):
    if not audio_file.content_type or not audio_file.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="오디오 파일만 업로드할 수 있습니다.",
        )

    select_question = (
        db.query(SelectQuestion)
        .filter(SelectQuestion.sel_id == sel_id, SelectQuestion.inter_id == inter_id)
        .first()
    )
    if not select_question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="세션에서 해당 질문을 찾을 수 없습니다.",
        )

    ext = resolve_recording_extension(audio_file.filename, audio_file.content_type)
    _, relative_path = build_recording_paths(inter_id, sel_id, ext)

    payload = await audio_file.read()
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="업로드한 오디오 파일이 비어 있습니다.",
        )

    saved = save_recording_and_upsert(
        db=db,
        inter_id=inter_id,
        sel_id=sel_id,
        filename=audio_file.filename,
        content_type=audio_file.content_type,
        payload=payload,
        duration_sec=duration_sec,
    )

    return {
        "message": "Recording uploaded.",
        "inter_id": inter_id,
        "sel_id": sel_id,
        "recording_id": saved.recording_id,
        "file_path": saved.file_path,
        "mime_type": saved.mime_type,
        "size_bytes": saved.size_bytes,
        "duration_sec": saved.duration_sec,
        "upload_status": saved.upload_status,
        "storage_rule_path": relative_path,
    }


@web_router.post(
    "/api/interviews/{inter_id}/questions/{sel_id}/stt",
    status_code=status.HTTP_200_OK,
)
async def run_stt(
    inter_id: int,
    sel_id: int,
    db: Session = Depends(get_db),
):
    select_question = (
        db.query(SelectQuestion)
        .filter(SelectQuestion.sel_id == sel_id, SelectQuestion.inter_id == inter_id)
        .first()
    )
    if not select_question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="세션에서 해당 질문을 찾을 수 없습니다.",
        )

    try:
        recording, transcript = run_stt_and_update(db=db, inter_id=inter_id, sel_id=sel_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"STT 처리에 실패했습니다: {exc}",
        ) from exc

    return {
        "message": "STT completed.",
        "inter_id": inter_id,
        "sel_id": sel_id,
        "recording_id": recording.recording_id,
        "upload_status": recording.upload_status,
        "transcript_id": transcript.transcript_id,
        "transcript_text": transcript.transcript_text,
    }


@web_router.post(
    "/api/interviews/{inter_id}/questions/{sel_id}/speech-score",
    status_code=status.HTTP_200_OK,
)
async def build_speech_score(
    inter_id: int,
    sel_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(
            SelectQuestion.sel_id.label("sel_id"),
            Question.qust_question_text.label("question_text"),
            AudioRecording.duration_sec.label("duration_sec"),
            Transcript.transcript_text.label("transcript_text"),
        )
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .outerjoin(AudioRecording, AudioRecording.sel_id == SelectQuestion.sel_id)
        .outerjoin(Transcript, Transcript.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == inter_id, SelectQuestion.sel_id == sel_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="세션에서 해당 질문을 찾을 수 없습니다.",
        )
    if not (row.transcript_text or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="전사 텍스트가 없습니다. 먼저 STT를 실행해 주세요.",
        )

    score_payload = calculate_speech_scores(
        transcript_text=row.transcript_text,
        duration_sec=int(row.duration_sec or 0),
        question_text=row.question_text,
    )
    summary = upsert_speech_summary(db=db, sel_id=sel_id, score=score_payload)
    upsert_speech_detail(db=db, sel_id=sel_id, score=score_payload)

    return {
        "message": "Speech score calculated.",
        "inter_id": inter_id,
        "sel_id": sel_id,
        "score_id": summary.score_id,
        "fluency_score": float(summary.sss_fluency_score),
        "clarity_score": float(summary.sss_clarity_score),
        "structure_score": float(summary.sss_structure_score),
        "length_score": float(summary.sss_length_score),
        "metrics": score_payload.metrics,
    }


@web_router.post(
    "/api/interviews/{inter_id}/submit-analysis",
    status_code=status.HTTP_200_OK,
)
async def submit_interview_analysis(
    inter_id: int,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            SelectQuestion.sel_id.label("sel_id"),
            SelectQuestion.sel_order_no.label("sel_order_no"),
            Question.qust_question_text.label("question_text"),
            AudioRecording.file_path.label("file_path"),
            AudioRecording.duration_sec.label("duration_sec"),
            Transcript.transcript_text.label("transcript_text"),
        )
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .outerjoin(AudioRecording, AudioRecording.sel_id == SelectQuestion.sel_id)
        .outerjoin(Transcript, Transcript.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == inter_id)
        .order_by(SelectQuestion.sel_order_no.asc(), SelectQuestion.sel_id.asc())
        .all()
    )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="면접 세션 질문을 찾을 수 없습니다.",
        )

    processed: list[dict[str, int | str]] = []
    failed: list[dict[str, int | str]] = []

    for row in rows:
        if not (row.file_path or "").strip():
            failed.append(
                {
                    "sel_id": int(row.sel_id),
                    "sel_order_no": int(row.sel_order_no),
                    "reason": "녹음 파일이 없습니다.",
                }
            )
            continue

        transcript_text = (row.transcript_text or "").strip()
        if not transcript_text:
            try:
                _, transcript = run_stt_and_update(db=db, inter_id=inter_id, sel_id=int(row.sel_id))
                transcript_text = (transcript.transcript_text or "").strip()
            except Exception as exc:
                failed.append(
                    {
                        "sel_id": int(row.sel_id),
                        "sel_order_no": int(row.sel_order_no),
                        "reason": str(exc),
                    }
                )
                continue

        if not transcript_text:
            failed.append(
                {
                    "sel_id": int(row.sel_id),
                    "sel_order_no": int(row.sel_order_no),
                    "reason": "전사 텍스트가 비어 있습니다.",
                }
            )
            continue

        score_payload = calculate_speech_scores(
            transcript_text=transcript_text,
            duration_sec=int(row.duration_sec or 0),
            question_text=row.question_text,
        )
        upsert_speech_summary(db=db, sel_id=int(row.sel_id), score=score_payload)
        upsert_speech_detail(db=db, sel_id=int(row.sel_id), score=score_payload)
        processed.append(
            {
                "sel_id": int(row.sel_id),
                "sel_order_no": int(row.sel_order_no),
            }
        )

    session = db.query(InterviewSession).filter(InterviewSession.inter_id == inter_id).first()
    if session and not failed:
        session.inter_status = "DONE"
        session.inter_finished_at = func.now()
        db.commit()

    return {
        "ok": len(failed) == 0,
        "inter_id": inter_id,
        "processed_count": len(processed),
        "failed_count": len(failed),
        "processed": processed,
        "failed": failed,
    }


@web_router.post(
    "/api/interviews/{inter_id}/submit-analysis/start",
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_submit_analysis_job(
    inter_id: int,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            SelectQuestion.sel_id.label("sel_id"),
            AudioRecording.recording_id.label("recording_id"),
        )
        .outerjoin(AudioRecording, AudioRecording.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == inter_id)
        .all()
    )
    total_questions = len(rows)
    recorded_questions = sum(1 for row in rows if row.recording_id is not None)

    if total_questions != 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"면접 질문은 5개여야 제출할 수 있습니다. (현재 {total_questions}개)",
        )
    if recorded_questions < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"5개 질문의 녹음을 모두 완료해 주세요. ({recorded_questions}/5 완료)",
        )

    with SUBMIT_ANALYSIS_LOCK:
        progress = SUBMIT_ANALYSIS_PROGRESS.get(inter_id)
        if progress and progress.get("status") == "running":
            return {
                "ok": True,
                "inter_id": inter_id,
                "status": "running",
                "message": "Analysis job is already running.",
            }
        SUBMIT_ANALYSIS_PROGRESS[inter_id] = {
            "status": "running",
            "done": False,
            "ok": False,
            "total": 0,
            "completed": 0,
            "failed_count": 0,
            "message": "작업을 준비 중입니다.",
            "started_at": int(time.time()),
        }

    worker = threading.Thread(target=_run_submit_analysis_job, args=(inter_id,), daemon=True)
    worker.start()
    return {
        "ok": True,
        "inter_id": inter_id,
        "status": "started",
    }


@web_router.get(
    "/api/interviews/{inter_id}/submit-analysis/progress",
    status_code=status.HTTP_200_OK,
)
async def get_submit_analysis_progress(
    inter_id: int,
):
    with SUBMIT_ANALYSIS_LOCK:
        progress = dict(SUBMIT_ANALYSIS_PROGRESS.get(inter_id, {}))

    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis job not found.",
        )

    total = int(progress.get("total") or 0)
    completed = int(progress.get("completed") or 0)
    percent = int((completed / total) * 100) if total > 0 else 0
    progress["percent"] = max(0, min(100, percent))
    progress["inter_id"] = inter_id
    return progress


@web_router.get(
    "/api/interviews/{inter_id}/questions/{sel_id}/speech-feedback",
    status_code=status.HTTP_200_OK,
)
async def get_speech_feedback_payload(
    inter_id: int,
    sel_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(SelectQuestion.sel_id.label("sel_id"))
        .filter(SelectQuestion.inter_id == inter_id, SelectQuestion.sel_id == sel_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="세션에서 해당 질문을 찾을 수 없습니다.",
        )

    feedback_row = get_speech_feedback(db=db, sel_id=sel_id)
    if not feedback_row:
        return {
            "exists": False,
            "inter_id": inter_id,
            "sel_id": sel_id,
        }
    return {
        "exists": True,
        "inter_id": inter_id,
        "sel_id": sel_id,
        "report_md": feedback_row.sfb_report_md,
        "coaching_md": feedback_row.sfb_coaching_md,
        "model": feedback_row.sfb_model,
    }


@web_router.post(
    "/api/interviews/{inter_id}/questions/{sel_id}/speech-feedback",
    status_code=status.HTTP_200_OK,
)
async def build_speech_feedback(
    inter_id: int,
    sel_id: int,
    force: int = Form(default=0),
    db: Session = Depends(get_db),
):
    row = (
        db.query(
            SelectQuestion.sel_id.label("sel_id"),
            Question.qust_question_text.label("question_text"),
        )
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .filter(SelectQuestion.inter_id == inter_id, SelectQuestion.sel_id == sel_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="세션에서 해당 질문을 찾을 수 없습니다.",
        )

    if not force:
        cached = get_speech_feedback(db=db, sel_id=sel_id)
        if cached:
            return {
                "cached": True,
                "inter_id": inter_id,
                "sel_id": sel_id,
                "report_md": cached.sfb_report_md,
                "coaching_md": cached.sfb_coaching_md,
                "model": cached.sfb_model,
            }

    score_payload = get_speech_detail_payload(db=db, sel_id=sel_id)
    if not score_payload:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="발화 지표가 없습니다. 먼저 제출 분석을 실행해 주세요.",
        )

    try:
        feedback_result = generate_speech_feedback(
            question_text=row.question_text or "",
            score_payload=score_payload,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"발화 피드백 생성에 실패했습니다: {exc}",
        ) from exc

    saved = upsert_speech_feedback(db=db, sel_id=sel_id, result=feedback_result)
    return {
        "cached": False,
        "inter_id": inter_id,
        "sel_id": sel_id,
        "report_md": saved.sfb_report_md,
        "coaching_md": saved.sfb_coaching_md,
        "model": saved.sfb_model,
    }
@web_router.post(
    "/api/interviews/{inter_id}/questions/{sel_id}/transcript/refine",
    status_code=status.HTTP_200_OK,
)
async def refine_transcript(
    inter_id: int,
    sel_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(
            SelectQuestion.sel_id.label("sel_id"),
            Transcript.transcript_text.label("transcript_text"),
        )
        .outerjoin(Transcript, Transcript.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == inter_id, SelectQuestion.sel_id == sel_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="세션에서 해당 질문을 찾을 수 없습니다.",
        )
    if not (row.transcript_text or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="전사 텍스트가 없습니다. 먼저 STT를 실행해 주세요.",
        )

    try:
        result = refine_transcript_with_guardrails(row.transcript_text)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"전사 텍스트 보정에 실패했습니다: {exc}",
        ) from exc

    saved = upsert_refine_result(db=db, sel_id=sel_id, result=result)
    return {
        "message": "Transcript refine completed.",
        "inter_id": inter_id,
        "sel_id": sel_id,
        "status": saved.r_status,
        "applied": saved.r_status == "APPLIED",
        "confidence": saved.r_refine_confidence,
        "changed_ratio": saved.r_changed_ratio,
        "reject_reason": saved.r_reject_reason,
        "raw_text": saved.r_raw_text,
        "refined_text": saved.r_refined_text,
    }


@web_router.get(
    "/api/interviews/{inter_id}/questions/{sel_id}/transcript",
    status_code=status.HTTP_200_OK,
)
async def get_transcript_payload(
    inter_id: int,
    sel_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(
            SelectQuestion.sel_id.label("sel_id"),
            Transcript.transcript_text.label("raw_text"),
            TranscriptRefine.r_refined_text.label("refined_text"),
            TranscriptRefine.r_status.label("refine_status"),
            TranscriptRefine.r_refine_confidence.label("refine_confidence"),
            TranscriptRefine.r_changed_ratio.label("changed_ratio"),
            TranscriptRefine.r_reject_reason.label("reject_reason"),
            TranscriptRefine.r_llm_model.label("llm_model"),
        )
        .outerjoin(Transcript, Transcript.sel_id == SelectQuestion.sel_id)
        .outerjoin(TranscriptRefine, TranscriptRefine.transcript_id == Transcript.transcript_id)
        .filter(SelectQuestion.inter_id == inter_id, SelectQuestion.sel_id == sel_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="세션에서 해당 질문을 찾을 수 없습니다.",
        )

    raw_text = row.raw_text or ""
    effective_text = raw_text
    source = "raw"
    if row.refine_status == "APPLIED" and (row.refined_text or "").strip():
        effective_text = row.refined_text
        source = "refined"

    return {
        "schema_version": "v1",
        "inter_id": inter_id,
        "sel_id": sel_id,
        "source": source,
        "effective_text": effective_text,
        "raw_text": raw_text,
        "refined_text": row.refined_text,
        "stt_meta": {
            "refine_status": row.refine_status,
            "refine_confidence": row.refine_confidence,
            "changed_ratio": row.changed_ratio,
            "reject_reason": row.reject_reason,
            "llm_model": row.llm_model,
        },
    }

@web_router.get("/result/analysis/text")
async def analysis_text(request: Request, session_id: int):
    return templates.TemplateResponse(
        "result/analysis_text.html",
        {"request": request, "session_id": session_id},
    )

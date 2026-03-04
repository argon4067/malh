from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.database import get_db
from models.user import User
from models.audio_recording import AudioRecording
from models.interview_session import InterviewSession
from models.question import Question
from models.resume import Resume
from models.select_question import SelectQuestion
from models.speech_score_summary import SpeechScoreSummary
from models.transcript import Transcript
from fastapi.responses import RedirectResponse

from services.resume_service import (
    DEFAULT_MODEL,
    analyze_saved_resume,
    create_resume_record,
    delete_resume,
    get_resume_analysis_result,
)
from services.speech_score_service import calculate_speech_scores, upsert_speech_summary

from services.stt_service import (
    build_recording_paths,
    resolve_recording_extension,
    run_stt_and_update,
    save_recording_and_upsert,
)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

web_router = APIRouter()

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
async def analyze_resume(
    request: Request,
    resume_id: int,
    model: str = Form(DEFAULT_MODEL),
    db: Session = Depends(get_db),
):
    user = _get_login_user(request, db)
    _get_owned_resume(db, user.user_id, resume_id)

    analyze_saved_resume(
        db=db,
        resume_id=resume_id,
        model=model,
    )
    return {"ok": True, "resume_id": resume_id}

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


# Interview
@web_router.get("/interviews/wait")
async def interview_wait(request: Request):
    return templates.TemplateResponse("interview/wait.html", {"request": request})


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

    return templates.TemplateResponse(
        "interview/questions.html",
        {
            "request": request,
            "session_id": session_id,
            "resume_id": _get_resume_id_by_session(db, session_id),
            "question_items": question_items,
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
            detail="Question in session not found.",
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
    return templates.TemplateResponse(
        "result/analysis.html",
        {"request": request, "session_id": session_id, "sel_id": sel_id},
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
            AudioRecording.duration_sec.label("duration_sec"),
            Transcript.t_transcript_text.label("transcript_text"),
            SpeechScoreSummary.sss_fluency_score.label("fluency_score"),
            SpeechScoreSummary.sss_clarity_score.label("clarity_score"),
            SpeechScoreSummary.sss_structure_score.label("structure_score"),
            SpeechScoreSummary.sss_length_score.label("length_score"),
        )
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .outerjoin(AudioRecording, AudioRecording.sel_id == SelectQuestion.sel_id)
        .outerjoin(Transcript, Transcript.sel_id == SelectQuestion.sel_id)
        .outerjoin(SpeechScoreSummary, SpeechScoreSummary.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == session_id, SelectQuestion.sel_id == sel_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question in session not found.",
        )

    transcript_text = (row.transcript_text or "").strip()
    duration_sec = int(row.duration_sec or 0)
    score_payload = None

    if transcript_text:
        score_payload = calculate_speech_scores(
            transcript_text=transcript_text,
            duration_sec=duration_sec,
        )
        upsert_speech_summary(db=db, sel_id=sel_id, score=score_payload)

    return templates.TemplateResponse(
        "result/analysis_stt.html",
        {
            "request": request,
            "session_id": session_id,
            "sel_id": sel_id,
            "question_text": row.question_text,
            "score": score_payload,
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
            Transcript.t_transcript_text.label("transcript_text"),
        )
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .outerjoin(AudioRecording, AudioRecording.sel_id == SelectQuestion.sel_id)
        .outerjoin(Transcript, Transcript.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == session_id, SelectQuestion.sel_id == sel_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript in session not found.",
        )

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
                "transcript_text": row.transcript_text or "Transcript is not generated yet.",
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
            detail="Weakness question in session not found.",
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
            detail="Only audio files are allowed.",
        )

    select_question = (
        db.query(SelectQuestion)
        .filter(SelectQuestion.sel_id == sel_id, SelectQuestion.inter_id == inter_id)
        .first()
    )
    if not select_question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question in session not found.",
        )

    ext = resolve_recording_extension(audio_file.filename, audio_file.content_type)
    _, relative_path = build_recording_paths(inter_id, sel_id, ext)

    payload = await audio_file.read()
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded audio file is empty.",
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
            detail="Question in session not found.",
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
            detail=f"STT processing failed: {exc}",
        ) from exc

    return {
        "message": "STT completed.",
        "inter_id": inter_id,
        "sel_id": sel_id,
        "recording_id": recording.recording_id,
        "upload_status": recording.upload_status,
        "transcript_id": transcript.transcript_id,
        "transcript_text": transcript.t_transcript_text,
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
            AudioRecording.duration_sec.label("duration_sec"),
            Transcript.t_transcript_text.label("transcript_text"),
        )
        .outerjoin(AudioRecording, AudioRecording.sel_id == SelectQuestion.sel_id)
        .outerjoin(Transcript, Transcript.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == inter_id, SelectQuestion.sel_id == sel_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question in session not found.",
        )
    if not (row.transcript_text or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transcript is missing. Run STT first.",
        )

    score_payload = calculate_speech_scores(
        transcript_text=row.transcript_text,
        duration_sec=int(row.duration_sec or 0),
    )
    summary = upsert_speech_summary(db=db, sel_id=sel_id, score=score_payload)

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
from fastapi import APIRouter, Request, Depends, File, Form, UploadFile, status, HTTPException
from sqlalchemy.orm import Session

from services.resume_service import (
    DEFAULT_MODEL,
    create_resume_record,
    analyze_saved_resume,
)

from fastapi.templating import Jinja2Templates
from pathlib import Path

from core.database import get_db
from models.audio_recording import AudioRecording
from models.interview_session import InterviewSession
from models.question import Question
from models.select_question import SelectQuestion
from models.transcript import Transcript
from services.stt_service import (
    build_recording_paths,
    resolve_recording_extension,
    save_recording_and_upsert,
)

from models.resume import Resume
from models.resume_classification import ResumeClassification
from models.resume_keyword import ResumeKeyword

# templates 폴더 경로 설정 (malh/templates)
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

web_router = APIRouter()


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
    resumes = (                      
        db.query(Resume)
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
    user_id: int = Form(...),
    model: str = Form(DEFAULT_MODEL),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    resume = create_resume_record(
        db=db,
        user_id=user_id,
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
    result = get_resume_analysis_result(db, resume_id)

    return templates.TemplateResponse(
        "resume/detail.html",
        {
            "request": request,
            "resume_id": resume_id,
            "resume": result["resume"],
            "classification": result["classification"],
            "keywords": result["keywords"],
        },
    )

@web_router.get("/resumes/{resume_id}/feedback")
async def resume_feedback(
    request: Request,
    resume_id: int,
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        "resume/feedback.html",
        {
            "request": request,
            "resume_id": resume_id,
            "session_id": _get_latest_session_id_by_resume(db, resume_id),
        },
    )

@web_router.post("/resumes/upload-analyze")
async def upload_and_analyze_resume(
    user_id: int = Form(...),
    model: str = Form(DEFAULT_MODEL),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    data = await file.read()

    return process_resume_upload_and_analyze(
        db=db,
        user_id=user_id,
        original_filename=file.filename or "resume.pdf",
        data=data,
        model=model,
    )

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
        .filter(SelectQuestion.inter_id == session_id, SelectQuestion.sel_id == question_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question in session not found.")

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
async def result_analysis_stt(request: Request, session_id: int, sel_id: int):
    return templates.TemplateResponse(
        "result/analysis_stt.html",
        {"request": request, "session_id": session_id, "sel_id": sel_id},
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript in session not found.")

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
                "transcript_text": row.transcript_text or "아직 변환된 텍스트가 없습니다.",
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
        .filter(SelectQuestion.inter_id == session_id, SelectQuestion.sel_id == question_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Weakness question in session not found.")

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

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session

from core.database import get_db
from models.audio_recording import AudioRecording
from models.question import Question
from models.select_question import SelectQuestion
from services.stt_service import (
    build_recording_paths,
    resolve_recording_extension,
    save_recording_and_upsert,
)

# templates 폴더 경로 설정 (malh/templates)
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

web_router = APIRouter()

@web_router.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Auth
@web_router.get("/auth/login")
async def login(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request, "resume_id": 1})

@web_router.get("/auth/agree")
async def agree(request: Request):
    return templates.TemplateResponse("auth/agree.html", {"request": request, "resume_id": 1})

@web_router.get("/auth/signup")
async def signup(request: Request):
    return templates.TemplateResponse("auth/signup.html", {"request": request, "resume_id": 1})

# Resume
@web_router.get("/resumes")
async def resume_list(request: Request):
    return templates.TemplateResponse("resume/list.html", {"request": request, "resume_id": 1})

@web_router.get("/resumes/wait")
async def resume_wait(request: Request):
    return templates.TemplateResponse("resume/wait.html", {"request": request, "resume_id": 1})

@web_router.get("/resumes/{resume_id}")
async def resume_detail(request: Request, resume_id: int):
    return templates.TemplateResponse("resume/detail.html", {"request": request, "resume_id": resume_id})

@web_router.get("/resumes/{resume_id}/feedback")
async def resume_feedback(request: Request, resume_id: int):
    return templates.TemplateResponse("resume/feedback.html", {"request": request, "resume_id": resume_id, "session_id": 1})

# Interview
@web_router.get("/interviews/wait")
async def interview_wait(request: Request):
    return templates.TemplateResponse("interview/wait.html", {"request": request, "resume_id": 1})

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
            "resume_id": 1,
            "question_items": question_items,
        },
    )

@web_router.get("/interviews/{session_id}/questions/{question_id}")
async def interview_question_detail(request: Request, session_id: int, question_id: int):
    return templates.TemplateResponse("interview/question_detail.html", {"request": request, "session_id": session_id, "question_id": question_id, "resume_id": 1})

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
            "resume_id": 1,
            "result_items": result_items,
        },
    )

@web_router.get("/interviews/{session_id}/results/{sel_id}/analysis")
async def result_analysis(request: Request, session_id: int, sel_id: int):
    return templates.TemplateResponse("result/analysis.html", {"request": request, "session_id": session_id, "sel_id": sel_id, "resume_id": 1})

@web_router.get("/interviews/{session_id}/results/{sel_id}/stt")
async def result_analysis_stt(request: Request, session_id: int, sel_id: int):
    return templates.TemplateResponse("result/analysis_stt.html", {"request": request, "session_id": session_id, "sel_id": sel_id, "resume_id": 1})

@web_router.get("/interviews/{session_id}/results/{sel_id}/text")
async def result_transcript(request: Request, session_id: int, sel_id: int):
    return templates.TemplateResponse("result/transcript.html", {"request": request, "session_id": session_id, "sel_id": sel_id, "resume_id": 1})

# Weakness
@web_router.get("/interviews/{session_id}/weakness")
async def weakness_questions(request: Request, session_id: int):
    return templates.TemplateResponse("weakness/questions.html", {"request": request, "session_id": session_id, "resume_id": 1})

@web_router.get("/interviews/{session_id}/weakness/wait")
async def weakness_wait(request: Request, session_id: int):
    return templates.TemplateResponse("weakness/wait.html", {"request": request, "session_id": session_id, "resume_id": 1})

@web_router.get("/interviews/{session_id}/weakness/{question_id}")
async def weakness_detail(request: Request, session_id: int, question_id: int):
    return templates.TemplateResponse("weakness/question_detail.html", {"request": request, "session_id": session_id, "question_id": question_id, "resume_id": 1})

# Account
@web_router.get("/account/password")
async def account_password(request: Request):
    return templates.TemplateResponse("account/password.html", {"request": request, "resume_id": 1})

@web_router.get("/account/withdraw")
async def account_withdraw(request: Request):
    return templates.TemplateResponse("account/withdraw.html", {"request": request, "resume_id": 1})


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

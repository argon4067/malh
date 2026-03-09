from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.config import settings
from core.database import engine
from models.base import Base
import models.answer_analysis
import models.audio_recording
import models.interview_session
import models.llm_run
import models.question
import models.question_filter_result
import models.question_set
import models.resume
import models.resume_classification
import models.resume_keyword
import models.select_question
import models.speech_score_detail
import models.speech_feedback
import models.speech_score_summary
import models.transcript

import models.user
from web.router import web_router
from core.logging import setup_logging
from services.storage_cleanup_service import prune_empty_audio_tree

from services.member_service import router as member_router
from services.feedback_service import router as feedback_router

Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

setup_logging()


def create_app() -> FastAPI:
    app = FastAPI(title="Mock Interview AI", version="0.1.0")

    static_dir = BASE_DIR / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.mount("/storage", StaticFiles(directory=settings.STORAGE_DIR), name="storage")

    app.include_router(web_router)
    app.include_router(member_router)
    app.include_router(feedback_router, tags=["feedback"])

    @app.on_event("startup")
    def prune_empty_audio_dirs_on_startup() -> None:
        # Auto-clean stale empty directories under storage/audio/interviews.
        try:
            prune_empty_audio_tree(Path(settings.STORAGE_DIR))
        except Exception:
            pass

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/health", response_class=HTMLResponse)
    def health():
        return "ok"

    return app


app = create_app()

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from pathlib import Path
import threading
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.config import settings
from core.database import SessionLocal, engine
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
from services.interview_cleanup_service import cleanup_stale_in_progress_session_audio

from services.member_service import router as member_router
from services.feedback_service import router as feedback_router

Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

setup_logging()
logger = logging.getLogger(__name__)


def cleanup_stale_interview_audio_once() -> None:
    db = SessionLocal()
    try:
        stale_before = datetime.now() - timedelta(seconds=settings.INTERVIEW_AUDIO_STALE_TTL_SEC)
        summary = cleanup_stale_in_progress_session_audio(db=db, stale_before=stale_before)
        if summary["stale_sessions"] > 0:
            logger.info(
                "STALE_AUDIO_CLEANUP sessions=%s removed_audio=%s removed_files=%s",
                summary["stale_sessions"],
                summary["removed_audio"],
                summary["removed_files"],
            )
    except Exception:
        logger.exception("STALE_AUDIO_CLEANUP_RUN_FAILED")
    finally:
        db.close()


def run_stale_interview_audio_cleanup_loop(stop_event: threading.Event) -> None:
    interval_sec = max(60, int(settings.INTERVIEW_AUDIO_CLEANUP_INTERVAL_SEC))

    while not stop_event.is_set():
        cleanup_stale_interview_audio_once()
        if stop_event.wait(interval_sec):
            break


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

        stop_event = threading.Event()
        cleanup_thread = threading.Thread(
            target=run_stale_interview_audio_cleanup_loop,
            args=(stop_event,),
            daemon=True,
            name="stale-audio-cleanup",
        )
        app.state.stale_audio_cleanup_stop_event = stop_event
        app.state.stale_audio_cleanup_thread = cleanup_thread
        cleanup_thread.start()

    @app.on_event("shutdown")
    def stop_stale_audio_cleanup_worker() -> None:
        stop_event = getattr(app.state, "stale_audio_cleanup_stop_event", None)
        cleanup_thread = getattr(app.state, "stale_audio_cleanup_thread", None)
        if stop_event is not None:
            stop_event.set()
        if cleanup_thread is not None and cleanup_thread.is_alive():
            cleanup_thread.join(timeout=1.0)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/health", response_class=HTMLResponse)
    def health():
        return "ok"

    return app


app = create_app()

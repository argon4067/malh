from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
import models.speech_feedback
import models.speech_score_detail
import models.speech_score_summary
import models.transcript
import models.user
from core.config import settings
from core.database import SessionLocal, engine
from core.logging import setup_logging
from models.base import Base
from services.feedback_service import router as feedback_router
from services.interview_cleanup_service import \
    cleanup_stale_in_progress_session_audio
from services.member_service import router as member_router
from services.storage_cleanup_service import prune_empty_audio_tree
from web.router import web_router

# DB 테이블 생성
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # [STARTUP] 오디오 디렉토리 정리 및 백그라운드 클린업 스레드 시작
    try:
        prune_empty_audio_tree(Path(settings.STORAGE_DIR))
    except Exception:
        logger.warning("Failed to prune empty audio tree on startup")

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
    logger.info("Startup complete: Stale audio cleanup thread started")

    yield

    # [SHUTDOWN] 백그라운드 스레드 안전하게 종료
    stop_event = getattr(app.state, "stale_audio_cleanup_stop_event", None)
    cleanup_thread = getattr(app.state, "stale_audio_cleanup_thread", None)
    if stop_event is not None:
        stop_event.set()
    if cleanup_thread is not None and cleanup_thread.is_alive():
        cleanup_thread.join(timeout=1.0)
    logger.info("Shutdown complete: Stale audio cleanup thread stopped")


from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.exceptions import BaseAPIException

def register_exception_handlers(app: FastAPI):
    @app.exception_handler(BaseAPIException)
    async def base_api_exception_handler(request: Request, exc: BaseAPIException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "ok": False,
                "code": exc.code,
                "detail": exc.detail,
                "data": exc.data,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        # API 요청인지 확인 (보통 /api/로 시작하거나 accept 헤더가 json인 경우)
        if request.url.path.startswith("/api/") or "application/json" in request.headers.get("accept", ""):
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "ok": False,
                    "code": f"HTTP_{exc.status_code}",
                    "detail": exc.detail,
                },
            )
        # 웹 페이지 요청인 경우 (기존 방식 유지 또는 에러 페이지 반환)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "ok": False,
                "code": "VALIDATION_ERROR",
                "detail": "입력값 검증에 실패했습니다.",
                "errors": exc.errors(),
            },
        )

def create_app() -> FastAPI:
    app = FastAPI(
        title="Mock Interview AI",
        version="0.1.0",
        lifespan=lifespan
    )

    register_exception_handlers(app)

    static_dir = BASE_DIR / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.mount("/storage", StaticFiles(directory=settings.STORAGE_DIR), name="storage")

    # 라우터 등록
    app.include_router(web_router)
    app.include_router(member_router)
    app.include_router(feedback_router, tags=["feedback"])

    @app.get("/health", response_class=HTMLResponse)
    def health():
        return "ok"

    return app


app = create_app()

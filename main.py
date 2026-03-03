from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

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
import models.speech_score_summary
import models.transcript
import models.user
from web.router import web_router

# 앱 시작 시 테이블 생성
Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent  # .../app


def create_app() -> FastAPI:
    app = FastAPI(title="Mock Interview AI", version="0.1.0")

    # ✅ 어디서 실행해도 static 경로가 깨지지 않게 절대경로로 마운트
    static_dir = BASE_DIR / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # SSR 라우터
    app.include_router(web_router)

    @app.get("/health", response_class=HTMLResponse)
    def health():
        return "ok"

    return app


app = create_app()

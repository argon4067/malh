from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

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

from services.member_service import router as member_router

# 앱 시작 시 테이블 생성
Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent  # .../app

# ✅ 템플릿 디렉토리 설정 (templates 폴더가 app/templates에 있다고 가정)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def create_app() -> FastAPI:
    app = FastAPI(title="Mock Interview AI", version="0.1.0")

    # ✅ 어디서 실행해도 static 경로가 깨지지 않게 절대경로로 마운트
    static_dir = BASE_DIR / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # SSR 라우터
    app.include_router(web_router)

    # 회원가입/로그인 라우터
    app.include_router(member_router)

    # ✅ 메인 페이지 경로 추가
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        # 템플릿에 request를 전달해야 index.html에서 쿠키를 읽을 수 있습니다.
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/health", response_class=HTMLResponse)
    def health():
        return "ok"

    return app


app = create_app()
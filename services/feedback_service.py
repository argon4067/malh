import os
import json
import logging
from typing import Optional, List

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from openai import OpenAI

# 프로젝트 설정 및 모델 임포트
from core.database import get_db
from models.resume import Resume
from models.resume_keyword import ResumeKeyword
from models.user import User   # ✅ 추가

from services.prompt.feedback.extract_company_prompt import (
    EXTRACT_COMPANY_SYSTEM_PROMPT,
    build_extract_company_user_prompt,
)
from services.prompt.feedback.analyze_feedback_prompt import (
    ANALYZE_FEEDBACK_SYSTEM_PROMPT,
    build_analyze_feedback_user_prompt,
)

logger = logging.getLogger(__name__)
load_dotenv()

templates = Jinja2Templates(directory="templates")

router = APIRouter()
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
    return OpenAI(api_key=api_key)


# -----------------------------------------------------
# 내부 로직 함수
# -----------------------------------------------------

def crawl_company_url(url: str) -> str:
    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        for s in soup(["script", "style"]):
            s.decompose()

        return "\n".join(
            line.strip()
            for line in soup.get_text().splitlines()
            if line.strip()
        )

    except Exception as e:
        logger.error(f"Crawl Error: {e}")
        return ""


def extract_company_info_llm(crawled_text: str, model: str = DEFAULT_MODEL) -> str:

    if not crawled_text or not crawled_text.strip():
        return json.dumps({
            "vision": "정보 없음",
            "core_values": [],
            "ideal_candidates": []
        })

    client = get_client()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": EXTRACT_COMPANY_SYSTEM_PROMPT},
                {"role": "user", "content": build_extract_company_user_prompt(crawled_text)},
            ],
            response_format={"type": "json_object"}
        )

        return response.choices[0].message.content

    except Exception:
        return json.dumps({
            "vision": "추출 실패",
            "core_values": [],
            "ideal_candidates": []
        })


def generate_feedback_llm(
        resume_keywords_json: str,
        company_info_json: str,
        required_stack: str,
        model: str = DEFAULT_MODEL
) -> dict:

    client = get_client()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": ANALYZE_FEEDBACK_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_analyze_feedback_user_prompt(
                        resume_keywords_json,
                        company_info_json,
                        required_stack
                    ),
                },
            ],
            response_format={"type": "json_object"}
        )

        return json.loads(response.choices[0].message.content)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 실패: {e}")


def get_resume_feedback(db: Session, resume_id: int, company_url: str, required_stack: str) -> dict:

    keywords = db.query(ResumeKeyword).filter(
        ResumeKeyword.resume_id == resume_id
    ).all()

    if not keywords:
        raise HTTPException(
            status_code=400,
            detail="이력서 키워드 데이터가 없습니다. 먼저 분석을 완료해 주세요."
        )

    resume_keywords_data = [
        {
            "type": kw.keyword_type,
            "keyword": kw.keyword_keyword,
            "evidence": kw.keyword_evidence
        }
        for kw in keywords
    ]

    resume_keywords_json = json.dumps(resume_keywords_data, ensure_ascii=False)

    crawled_text = crawl_company_url(company_url)

    company_info_json = extract_company_info_llm(crawled_text)

    return generate_feedback_llm(
        resume_keywords_json,
        company_info_json,
        required_stack
    )


# -----------------------------------------------------
# 라우터 엔드포인트
# -----------------------------------------------------

@router.get("/feedback")
async def feedback_page(request: Request, db: Session = Depends(get_db)):
    try:

        # ✅ 로그인 사용자 가져오기
        login_user = request.cookies.get("login_user")

        if not login_user:
            raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

        # ✅ username으로 user 조회
        user = db.query(User).filter(
            User.user_username == login_user
        ).first()

        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

        # ✅ 해당 user의 이력서만 조회
        resumes = db.query(Resume).filter(
            Resume.user_id == user.user_id
        ).all()

        # 기존 코드 유지
        has_resumes = len(resumes) > 0

        return templates.TemplateResponse(
            "/resume/feedback.html",
            {
                "request": request,
                "resumes": resumes,
                "has_resumes": has_resumes
            }
        )

    except Exception as e:
        logger.error(f"GET Feedback Page Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def analyze_feedback_api(payload: dict, db: Session = Depends(get_db)):

    resume_id = payload.get("resume_id")
    company_url = payload.get("company_url")
    required_stack = payload.get("companyStack")

    if not all([resume_id, company_url, required_stack]):
        raise HTTPException(status_code=400, detail="모든 정보를 입력해주세요.")

    return get_resume_feedback(
        db,
        int(resume_id),
        company_url,
        required_stack
    )
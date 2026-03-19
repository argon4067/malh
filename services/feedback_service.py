import os
import json
import logging
import hashlib
import time  # ✅ 추가
from typing import Optional, List

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from openai import OpenAI

from core.database import get_db
from models.resume import Resume
from models.resume_keyword import ResumeKeyword
from models.user import User

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


feedback_cache = {}
company_cache = {}

CACHE_TTL = 60 * 10


def get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
    return OpenAI(api_key=api_key)


def normalize_text(text: str) -> str:
    return " ".join(text.split())


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

        raw_text = "\n".join(
            line.strip()
            for line in soup.get_text().splitlines()
            if line.strip()
        )

        return normalize_text(raw_text)

    except Exception as e:
        logger.error(f"Crawl Error: {e}")
        return ""


def make_cache_key(*args) -> str:
    raw = "".join(args)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_company_info_llm(crawled_text: str, company_url: str, model: str = DEFAULT_MODEL) -> str:

    if not crawled_text or not crawled_text.strip():
        return json.dumps({
            "vision": "정보 없음",
            "core_values": [],
            "ideal_candidates": []
        })

    cache_key = make_cache_key(company_url)

    if cache_key in company_cache:
        cached_result, cached_time = company_cache[cache_key]

        if time.time() - cached_time < CACHE_TTL:
            return cached_result
        else:
            del company_cache[cache_key]

    client = get_client()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": EXTRACT_COMPANY_SYSTEM_PROMPT},
                {"role": "user", "content": build_extract_company_user_prompt(crawled_text)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            top_p=0,
        )

        result = response.choices[0].message.content

        # ✅ 캐시 저장 (시간 포함)
        company_cache[cache_key] = (result, time.time())

        return result

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

    cache_key = make_cache_key(
        resume_keywords_json,
        company_info_json,
        required_stack
    )

    if cache_key in feedback_cache:
        cached_result, cached_time = feedback_cache[cache_key]

        if time.time() - cached_time < CACHE_TTL:
            return cached_result
        else:
            del feedback_cache[cache_key]

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
            response_format={"type": "json_object"},
            temperature=0,
            top_p=0,
        )

        result = json.loads(response.choices[0].message.content)

        # ✅ 캐시 저장 (시간 포함)
        feedback_cache[cache_key] = (result, time.time())

        return result

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

    company_info_json = extract_company_info_llm(crawled_text, company_url)

    return generate_feedback_llm(
        resume_keywords_json,
        company_info_json,
        required_stack
    )


@router.get("/feedback")
async def feedback_page(request: Request, db: Session = Depends(get_db)):
    try:

        login_user = request.cookies.get("login_user")

        user = db.query(User).filter(
            User.user_username == login_user
        ).first()

        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

        resumes = db.query(Resume).filter(
            Resume.user_id == user.user_id
        ).all()

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
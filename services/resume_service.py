import hashlib
import io
import os
import re
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import HTTPException
from openai import OpenAI
from sqlalchemy.orm import Session

from models.resume import Resume
from models.resume_classification import ResumeClassification
from models.resume_keyword import ResumeKeyword
from models.llm_run import LlmRun
from schemas.resume_llm import (
    ResumeClassificationResult,
    ResumeKeywordItem,
    ResumeKeywordResult,
)
from services.prompt.resume.classify_prompt import (
    PROMPT_VERSION_CLASSIFY,
    CLASSIFY_SYSTEM_PROMPT,
    build_classify_user_prompt,
)
from services.prompt.resume.keyword_prompt import (
    PROMPT_VERSION_KEYWORD,
    KEYWORD_SYSTEM_PROMPT,
    build_keyword_user_prompt,
)

load_dotenv()

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_file_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".pdf":
        return "PDF"
    if ext == ".docx":
        return "DOCX"

    raise HTTPException(
        status_code=400,
        detail="PDF/DOCX만 업로드 가능합니다.",
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_pdf_text(data: bytes) -> str:
    try:
        import fitz
    except Exception as e:
        raise RuntimeError("pymupdf가 필요합니다.") from e

    doc = fitz.open(stream=data, filetype="pdf")
    return "\n".join(page.get_text("text") for page in doc)


def extract_docx_text(data: bytes) -> str:
    try:
        from docx import Document
    except Exception as e:
        raise RuntimeError("python-docx가 필요합니다.") from e

    doc = Document(io.BytesIO(data))
    parts: List[str] = []

    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if t:
            parts.append(t)

    for table in doc.tables:
        for row in table.rows:
            cells = [(c.text or "").strip() for c in row.cells]
            cells = [c for c in cells if c]
            if cells:
                parts.append(" | ".join(cells))

    return "\n".join(parts)


def extract_text_from_upload(filename: str, data: bytes) -> str:
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".pdf":
        return extract_pdf_text(data)

    if ext == ".docx":
        return extract_docx_text(data)

    raise HTTPException(status_code=400, detail="지원하지 않는 파일 형식입니다.")


def get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 없습니다.")
    return OpenAI(api_key=api_key)


def save_llm_run_success(
    db: Session,
    stage: str,
    model: str,
    prompt_version: str,
) -> LlmRun:
    row = LlmRun(
        llm_stage=stage,
        llm_model=model,
        llm_prompt_version=prompt_version,
        llm_status="SUCCESS",
        error_code=None,
        error_message=None,
    )
    db.add(row)
    db.flush()
    return row


def save_llm_run_failed(
    db: Session,
    stage: str,
    model: str,
    prompt_version: str,
    error_code: str,
    error_message: str,
) -> None:
    row = LlmRun(
        llm_stage=stage,
        llm_model=model,
        llm_prompt_version=prompt_version,
        llm_status="FAILED",
        error_code=error_code,
        error_message=(error_message or "")[:255] or None,
    )
    db.add(row)
    db.flush()

def create_resume_record(
    db: Session,
    user_id: int,
    original_filename: str,
    data: bytes,
) -> Resume:
    file_type = detect_file_type(original_filename)
    extracted_text = normalize_text(extract_text_from_upload(original_filename, data))

    if not extracted_text:
        raise HTTPException(status_code=400, detail="텍스트를 추출하지 못했습니다.")

    if len(extracted_text) > 80000:
        extracted_text = extracted_text[:80000] + "\n\n[TRUNCATED]"

    resume = Resume(
        user_id=user_id,
        resume_file_name=original_filename,
        resume_file_type=file_type,
        resume_file_path=None,
        resume_file_size=len(data),
        resume_extracted_text=extracted_text,
        resume_sha256=sha256_bytes(data),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


def get_resume_by_id(db: Session, resume_id: int) -> Resume:
    resume = db.query(Resume).filter(Resume.resume_id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="이력서를 찾을 수 없습니다.")
    return resume

def get_resume_analysis_result(db: Session, resume_id: int):
    resume = get_resume_by_id(db, resume_id)

    classification = (
        db.query(ResumeClassification)
        .filter(ResumeClassification.resume_id == resume_id)
        .first()
    )

    keywords = (
        db.query(ResumeKeyword)
        .filter(ResumeKeyword.resume_id == resume_id)
        .order_by(ResumeKeyword.keyword_id.asc())
        .all()
    )

    return {
        "resume": resume,
        "classification": classification,
        "keywords": keywords,
    }


def classify_resume_llm(
    resume_text: str,
    model: str = DEFAULT_MODEL,
) -> ResumeClassificationResult:
    client = get_client()

    resp = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
            {"role": "user", "content": build_classify_user_prompt(resume_text)},
        ],
        text_format=ResumeClassificationResult,
        truncation="auto",
    )

    if resp.output_parsed is None:
        raise RuntimeError("이력서 분류 파싱 실패")

    return resp.output_parsed


def analyze_resume_keywords_llm(
    resume_text: str,
    job_family: str,
    job_role: Optional[str],
    model: str = DEFAULT_MODEL,
) -> ResumeKeywordResult:
    client = get_client()

    resp = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": KEYWORD_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_keyword_user_prompt(
                    resume_text=resume_text,
                    job_family=job_family,
                    job_role=job_role,
                ),
            },
        ],
        text_format=ResumeKeywordResult,
        truncation="auto",
    )

    if resp.output_parsed is None:
        raise RuntimeError("이력서 키워드 분석 파싱 실패")

    return resp.output_parsed


def dedupe_keywords(items: List[ResumeKeywordItem]) -> List[ResumeKeywordItem]:
    result: List[ResumeKeywordItem] = []
    seen = set()

    for item in items:
        keyword = (item.keyword or "").strip()
        if not keyword:
            continue

        key = (keyword.lower(), item.keyword_type)
        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result

def analyze_saved_resume(
    db: Session,
    resume_id: int,
    model: str = DEFAULT_MODEL,
) -> None:
    resume = get_resume_by_id(db, resume_id)

    classification_exists = (
        db.query(ResumeClassification)
        .filter(ResumeClassification.resume_id == resume_id)
        .first()
    )
    keyword_exists = (
        db.query(ResumeKeyword)
        .filter(ResumeKeyword.resume_id == resume_id)
        .first()
    )

    if classification_exists and keyword_exists:
        return

    try:
        classification_result = classify_resume_llm(
            resume_text=resume.resume_extracted_text,
            model=model,
        )

        classify_run = save_llm_run_success(
            db=db,
            stage="RESUME_CLASSIFY",
            model=model,
            prompt_version=PROMPT_VERSION_CLASSIFY,
        )

        classification_row = ResumeClassification(
            resume_id=resume.resume_id,
            llm_id=classify_run.llm_id,
            class_job_family=classification_result.job_family,
            class_job_role=classification_result.job_role,
            class_evidence=[x.model_dump() for x in classification_result.evidence],
        )
        db.add(classification_row)
        db.commit()
        db.refresh(classification_row)

    except Exception as e:
        db.rollback()
        save_llm_run_failed(
            db=db,
            stage="RESUME_CLASSIFY",
            model=model,
            prompt_version=PROMPT_VERSION_CLASSIFY,
            error_code=type(e).__name__,
            error_message=str(e),
        )
        db.commit()
        raise HTTPException(status_code=500, detail=f"이력서 분류 실패: {e}") from e

    try:
        keyword_result = analyze_resume_keywords_llm(
            resume_text=resume.resume_extracted_text,
            job_family=classification_row.class_job_family,
            job_role=classification_row.class_job_role,
            model=model,
        )

        deduped = dedupe_keywords(keyword_result.keywords)

        keyword_run = save_llm_run_success(
            db=db,
            stage="RESUME_KEYWORD",
            model=model,
            prompt_version=PROMPT_VERSION_KEYWORD,
        )

        for item in deduped:
            db.add(
                ResumeKeyword(
                    resume_id=resume.resume_id,
                    llm_id=keyword_run.llm_id,
                    keyword_keyword=item.keyword,
                    keyword_type=item.keyword_type,
                    keyword_evidence=[x.model_dump() for x in item.evidence],
                )
            )

        db.commit()

    except Exception as e:
        db.rollback()
        save_llm_run_failed(
            db=db,
            stage="RESUME_KEYWORD",
            model=model,
            prompt_version=PROMPT_VERSION_KEYWORD,
            error_code=type(e).__name__,
            error_message=str(e),
        )
        db.commit()
        raise HTTPException(status_code=500, detail=f"이력서 키워드 분석 실패: {e}") from e
import hashlib
import io
import os
import re
from typing import List, Optional
import json

from dotenv import load_dotenv
from fastapi import HTTPException
from openai import OpenAI
from sqlalchemy.orm import Session

from models.llm_run import LlmRun
from models.resume import Resume
from models.resume_classification import ResumeClassification
from models.resume_keyword import ResumeKeyword
from schemas.resume_llm import (
    ResumeClassificationResult,
    ResumeKeywordItem,
    ResumeKeywordResult,
)
from services.prompt.resume.classify_prompt_v2 import (
    PROMPT_VERSION_CLASSIFY,
    CLASSIFY_SYSTEM_PROMPT,
    build_classify_user_prompt,
)
from services.prompt.resume.keyword_prompt_v2 import (
    PROMPT_VERSION_KEYWORD,
    KEYWORD_SYSTEM_PROMPT,
    build_keyword_user_prompt,
)

from models.resume_structured import ResumeStructured
from schemas.resume_structured import ResumeStructuredResult
from services.prompt.resume.structure_prompt import (
    PROMPT_VERSION_STRUCTURE,
    STRUCTURE_SYSTEM_PROMPT,
    build_structure_user_prompt,
)

load_dotenv()

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


class ResumeFileError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


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

    doc = None
    try:
        doc = fitz.open(stream=data, filetype="pdf")

        # 실제 비밀번호 입력이 필요한 PDF만 차단
        if getattr(doc, "needs_pass", False):
            raise ResumeFileError("암호가 설정된 PDF는 업로드할 수 없습니다.", 400)

        # 암호화 플래그만 있고 읽기 가능한 경우가 있어 추가 확인
        if getattr(doc, "is_encrypted", False):
            auth_result = doc.authenticate("")
            if auth_result == 0 and getattr(doc, "needs_pass", False):
                raise ResumeFileError("암호가 설정된 PDF는 업로드할 수 없습니다.", 400)

        parts: List[str] = []
        for page in doc:
            page_text = page.get_text("text") or ""
            if page_text.strip():
                parts.append(page_text)

        text = "\n".join(parts).strip()

        if not text:
            raise ResumeFileError(
                "PDF에서 텍스트를 추출하지 못했습니다. 스캔본, 이미지형 PDF, 또는 손상된 PDF일 수 있습니다.",
                400,
            )

        return text

    except ResumeFileError:
        raise
    except Exception as e:
        raise ResumeFileError(f"PDF 파싱 실패: {e}", 400) from e
    finally:
        if doc is not None:
            doc.close()


def extract_docx_text(data: bytes) -> str:
    try:
        from docx import Document
    except Exception as e:
        raise RuntimeError("python-docx가 필요합니다.") from e

    try:
        doc = Document(io.BytesIO(data))
    except Exception as e:
        raise ResumeFileError(
            "DOCX를 열 수 없습니다. 암호로 보호되었거나 손상된 파일일 수 있습니다.",
            400,
        ) from e

    try:
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

        text = "\n".join(parts).strip()

        if not text:
            raise ResumeFileError(
                "DOCX에서 텍스트를 추출하지 못했습니다. 비어 있거나 읽을 수 없는 문서입니다.",
                400,
            )

        return text

    except ResumeFileError:
        raise
    except Exception as e:
        raise ResumeFileError(f"DOCX 파싱 실패: {e}", 400) from e


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

    try:
        extracted_text = normalize_text(
            extract_text_from_upload(original_filename, data)
        )
    except ResumeFileError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e

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

    structured = (
        db.query(ResumeStructured)
        .filter(ResumeStructured.resume_id == resume_id)
        .first()
    )

    return {
        "resume": resume,
        "classification": classification,
        "keywords": keywords,
        "structured": structured,
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

def analyze_resume_structure_llm(
    resume_text: str,
    job_family: Optional[str],
    job_role: Optional[str],
    model: str = DEFAULT_MODEL,
) -> ResumeStructuredResult:
    client = get_client()

    resp = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": STRUCTURE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_structure_user_prompt(
                    resume_text=resume_text,
                    job_family=job_family,
                    job_role=job_role,
                ),
            },
        ],
        text_format=ResumeStructuredResult,
        truncation="auto",
    )

    if resp.output_parsed is None:
        raise RuntimeError("이력서 구조화 분석 파싱 실패")

    return resp.output_parsed


def analyze_resume_keywords_llm(
    structured_payload: dict,
    job_family: Optional[str],
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
                    structured_json=json.dumps(structured_payload, ensure_ascii=False, indent=2),
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

    structure_exists = (
    db.query(ResumeStructured)
    .filter(ResumeStructured.resume_id == resume_id)
    .first()
    )

    keyword_exists = (
        db.query(ResumeKeyword)
        .filter(ResumeKeyword.resume_id == resume_id)
        .first()
    )

    if classification_exists and keyword_exists and structure_exists:
        return

    classification_row = classification_exists

    if not classification_exists:
        try:
            classification_result = classify_resume_llm(
                resume_text=resume.resume_extracted_text,
                model=model,
            )

            classify_run = save_llm_run_success(
                db=db,
                stage="RESUME_CLASSIFY_V2",
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
                stage="RESUME_CLASSIFY_V2",
                model=model,
                prompt_version=PROMPT_VERSION_CLASSIFY,
                error_code=type(e).__name__,
                error_message=str(e),
            )
            db.commit()
            raise HTTPException(status_code=500, detail=f"이력서 분류 실패: {e}") from e
        
    if not structure_exists:
        try:
            structure_result = analyze_resume_structure_llm(
                resume_text=resume.resume_extracted_text,
                job_family=classification_row.class_job_family if classification_row else None,
                job_role=classification_row.class_job_role if classification_row else None,
                model=model,
            )

            structure_run = save_llm_run_success(
                db=db,
                stage="RESUME_STRUCTURE_V1",
                model=model,
                prompt_version=PROMPT_VERSION_STRUCTURE,
            )

            structure_row = ResumeStructured(
                resume_id=resume.resume_id,
                llm_id=structure_run.llm_id,
                structured_position=structure_result.position,
                structured_career_summary=(structure_result.career_summary or "")[:1000] or None,
                structured_skills=structure_result.skills,
                structured_educations=[x.model_dump() for x in structure_result.educations],
                structured_experiences=[x.model_dump() for x in structure_result.experiences],
                structured_projects=[x.model_dump() for x in structure_result.projects],
                structured_certificates=[x.model_dump() for x in structure_result.certificates],
            )
            db.add(structure_row)
            db.commit()

        except Exception as e:
            db.rollback()
            save_llm_run_failed(
                db=db,
                stage="RESUME_STRUCTURE_V1",
                model=model,
                prompt_version=PROMPT_VERSION_STRUCTURE,
                error_code=type(e).__name__,
                error_message=str(e),
            )
            db.commit()
            raise HTTPException(status_code=500, detail=f"이력서 구조화 분석 실패: {e}") from e

    if not keyword_exists:
        try:
            structured_payload = build_structured_payload(structure_row)

            keyword_result = analyze_resume_keywords_llm(
                structured_payload=structured_payload,
                job_family=classification_row.class_job_family if classification_row else None,
                job_role=classification_row.class_job_role if classification_row else None,
                model=model,
            )

            deduped = dedupe_keywords(keyword_result.keywords)

            keyword_run = save_llm_run_success(
                db=db,
                stage="RESUME_KEYWORD_V2",
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
                stage="RESUME_KEYWORD_V2",
                model=model,
                prompt_version=PROMPT_VERSION_KEYWORD,
                error_code=type(e).__name__,
                error_message=str(e),
            )
            db.commit()
            raise HTTPException(status_code=500, detail=f"이력서 키워드 분석 실패: {e}") from e
        
def delete_resume(db: Session, resume_id: int) -> None:
    resume = db.query(Resume).filter(Resume.resume_id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="이력서를 찾을 수 없습니다.")

    try:
        db.query(ResumeClassification).filter(
            ResumeClassification.resume_id == resume_id
        ).delete(synchronize_session=False)

        db.query(ResumeStructured).filter(
            ResumeStructured.resume_id == resume_id
        ).delete(synchronize_session=False)

        db.query(ResumeKeyword).filter(
            ResumeKeyword.resume_id == resume_id
        ).delete(synchronize_session=False)

        db.delete(resume)
        db.commit()

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"이력서 삭제 실패: {e}") from e
    
def build_structured_payload(structured_row: ResumeStructured) -> dict:
    return {
        "position": structured_row.structured_position,
        "career_summary": structured_row.structured_career_summary,
        "skills": structured_row.structured_skills or [],
        "educations": structured_row.structured_educations or [],
        "experiences": structured_row.structured_experiences or [],
        "projects": structured_row.structured_projects or [],
        "certificates": structured_row.structured_certificates or [],
    }

import json
import os
import re
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import HTTPException
from openai import OpenAI
from sqlalchemy.orm import Session

from models.llm_run import LlmRun
from models.resume import Resume
from models.resume_classification import ResumeClassification
from models.resume_structured import ResumeStructured
from models.question_set import QuestionSet
from models.question import Question
from models.question_filter_result import QuestionFilterResult

from schemas.question_llm import (
    QuestionCandidateItem,
    QuestionCandidateResult,
)

from services.prompt.question.generate_prompt import (
    PROMPT_VERSION_QUESTION_GENERATE,
    QUESTION_GENERATE_SYSTEM_PROMPT,
    build_question_generate_user_prompt,
)

load_dotenv()

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


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


def get_resume_by_id(db: Session, resume_id: int) -> Resume:
    resume = db.query(Resume).filter(Resume.resume_id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="이력서를 찾을 수 없습니다.")
    return resume


def get_resume_question_context(
    db: Session,
    resume_id: int,
):
    resume = get_resume_by_id(db, resume_id)

    classification = (
        db.query(ResumeClassification)
        .filter(ResumeClassification.resume_id == resume_id)
        .first()
    )

    structured = (
        db.query(ResumeStructured)
        .filter(ResumeStructured.resume_id == resume_id)
        .first()
    )

    if not structured:
        raise HTTPException(
            status_code=400,
            detail="이력서 구조화 데이터가 없습니다. 먼저 이력서 분석을 완료해야 합니다.",
        )

    return {
        "resume": resume,
        "classification": classification,
        "structured": structured,
    }


def build_question_structured_payload(structured_row: ResumeStructured) -> dict:
    return {
        "position": structured_row.structured_position,
        "career_summary": structured_row.structured_career_summary,
        "skills": structured_row.structured_skills or [],
        "educations": structured_row.structured_educations or [],
        "experiences": structured_row.structured_experiences or [],
        "projects": structured_row.structured_projects or [],
        "certificates": structured_row.structured_certificates or [],
    }


def normalize_question_text(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def calc_jaccard_similarity(text1: str, text2: str) -> float:
    a = set(normalize_question_text(text1).split())
    b = set(normalize_question_text(text2).split())

    if not a or not b:
        return 0.0

    union = a | b
    inter = a & b
    if not union:
        return 0.0

    return round(len(inter) / len(union), 3)


def is_yesno_question(text: str) -> bool:
    text = normalize_question_text(text)
    patterns = [
        "있습니까?",
        "인가요?",
        "했나요?",
        "가능한가요?",
        "아시나요?",
        "맞나요?",
    ]
    return any(text.endswith(p) for p in patterns)


def generate_question_candidates_llm(
    structured_payload: dict,
    job_family: Optional[str],
    job_role: Optional[str],
    purpose: str,
    count: int,
    existing_questions: List[str],
    model: str = DEFAULT_MODEL,
) -> QuestionCandidateResult:
    client = get_client()

    existing_questions_text = "\n".join(
        [f"- {q}" for q in existing_questions]
    ).strip()

    resp = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": QUESTION_GENERATE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_question_generate_user_prompt(
                    structured_json=json.dumps(
                        structured_payload,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    job_family=job_family,
                    job_role=job_role,
                    purpose=purpose,
                    count=count,
                    existing_questions_text=existing_questions_text,
                ),
            },
        ],
        text_format=QuestionCandidateResult,
        truncation="auto",
    )

    if resp.output_parsed is None:
        raise RuntimeError("질문 생성 파싱 실패")

    return resp.output_parsed


def create_question_set(
    db: Session,
    resume_id: int,
    purpose: str,
) -> QuestionSet:
    row = QuestionSet(
        resume_id=resume_id,
        set_attempt=1,
        set_status="GENERATING",
        set_purpose=purpose,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def save_question_candidates(
    db: Session,
    set_id: int,
    items: List[QuestionCandidateItem],
) -> None:
    for item in items:
        row = Question(
            set_id=set_id,
            qust_category=item.category,
            qust_difficulty=item.difficulty,
            qust_question_text=normalize_question_text(item.question_text),
            qust_evidence=item.evidence,
            qust_is_selected=0,
        )
        db.add(row)

    db.commit()


def get_selected_question_texts(
    db: Session,
    set_id: int,
) -> List[str]:
    rows = (
        db.query(Question.qust_question_text)
        .filter(
            Question.set_id == set_id,
            Question.qust_is_selected == 1,
        )
        .all()
    )
    return [row[0] for row in rows]


def count_selected_questions(
    db: Session,
    set_id: int,
) -> int:
    return (
        db.query(Question)
        .filter(
            Question.set_id == set_id,
            Question.qust_is_selected == 1,
        )
        .count()
    )


def filter_question_candidates(
    db: Session,
    set_id: int,
) -> None:
    question_set = (
        db.query(QuestionSet)
        .filter(QuestionSet.set_id == set_id)
        .first()
    )
    if not question_set:
        raise HTTPException(status_code=404, detail="질문 세트를 찾을 수 없습니다.")

    question_set.set_status = "FILTERING"
    db.commit()

    selected_questions = (
        db.query(Question)
        .filter(
            Question.set_id == set_id,
            Question.qust_is_selected == 1,
        )
        .order_by(Question.qust_id.asc())
        .all()
    )
    selected_texts = [q.qust_question_text for q in selected_questions]

    pending_questions = (
        db.query(Question)
        .filter(
            Question.set_id == set_id,
            Question.qust_is_selected == 0,
        )
        .order_by(Question.qust_id.asc())
        .all()
    )

    for question in pending_questions:
        already_filtered = (
            db.query(QuestionFilterResult)
            .filter(QuestionFilterResult.qust_id == question.qust_id)
            .first()
        )
        if already_filtered:
            continue

        reasons = []
        duplicate_similarity = None

        text = normalize_question_text(question.qust_question_text)
        evidence = question.qust_evidence or []

        if not text:
            reasons.append("MISSING_FIELD")

        if len(text) < 10:
            reasons.append("TOO_SHORT")

        if not evidence:
            reasons.append("EVIDENCE_EMPTY")

        if is_yesno_question(text):
            reasons.append("YESNO_OVER_QUOTA")

        max_sim = 0.0
        for selected_text in selected_texts:
            sim = calc_jaccard_similarity(text, selected_text)
            if sim > max_sim:
                max_sim = sim

        duplicate_similarity = round(max_sim, 3) if selected_texts else None

        if duplicate_similarity is not None and duplicate_similarity >= 0.8:
            reasons.append("DUPLICATE")

        if reasons:
            question.qust_is_selected = 0
            db.add(
                QuestionFilterResult(
                    qust_id=question.qust_id,
                    qfr_reasons=reasons,
                    qfr_duplicate_similarity=duplicate_similarity,
                )
            )
        else:
            question.qust_is_selected = 1
            selected_texts.append(text)

    db.commit()


def generate_questions_for_resume(
    db: Session,
    resume_id: int,
    target_count: int = 30,
    purpose: str = "DEFAULT",
    model: str = DEFAULT_MODEL,
) -> QuestionSet:
    context = get_resume_question_context(db, resume_id)
    classification = context["classification"]
    structured = context["structured"]

    structured_payload = build_question_structured_payload(structured)

    question_set = create_question_set(
        db=db,
        resume_id=resume_id,
        purpose=purpose,
    )

    try:
        # 1차 생성
        first_result = generate_question_candidates_llm(
            structured_payload=structured_payload,
            job_family=classification.class_job_family if classification else None,
            job_role=classification.class_job_role if classification else None,
            purpose=purpose,
            count=50,
            existing_questions=[],
            model=model,
        )

        save_llm_run_success(
            db=db,
            stage="QUESTION_GENERATE_V1",
            model=model,
            prompt_version=PROMPT_VERSION_QUESTION_GENERATE,
        )

        save_question_candidates(
            db=db,
            set_id=question_set.set_id,
            items=first_result.questions,
        )

        filter_question_candidates(
            db=db,
            set_id=question_set.set_id,
        )

        selected_count = count_selected_questions(
            db=db,
            set_id=question_set.set_id,
        )

        # 부족하면 최대 1회 추가 생성
        if selected_count < target_count:
            question_set.set_attempt = 2
            question_set.set_status = "GENERATING"
            db.commit()

            existing_questions = get_selected_question_texts(
                db=db,
                set_id=question_set.set_id,
            )

            retry_result = generate_question_candidates_llm(
                structured_payload=structured_payload,
                job_family=classification.class_job_family if classification else None,
                job_role=classification.class_job_role if classification else None,
                purpose=purpose,
                count=50,
                existing_questions=existing_questions,
                model=model,
            )

            save_llm_run_success(
                db=db,
                stage="QUESTION_GENERATE_RETRY_V1",
                model=model,
                prompt_version=PROMPT_VERSION_QUESTION_GENERATE,
            )

            save_question_candidates(
                db=db,
                set_id=question_set.set_id,
                items=retry_result.questions,
            )

            filter_question_candidates(
                db=db,
                set_id=question_set.set_id,
            )

        question_set.set_status = "COMPLETED"
        db.commit()
        db.refresh(question_set)
        return question_set

    except Exception as e:
        db.rollback()

        save_llm_run_failed(
            db=db,
            stage="QUESTION_GENERATE_V1",
            model=model,
            prompt_version=PROMPT_VERSION_QUESTION_GENERATE,
            error_code=type(e).__name__,
            error_message=str(e),
        )
        db.commit()

        question_set = (
            db.query(QuestionSet)
            .filter(QuestionSet.set_id == question_set.set_id)
            .first()
        )
        if question_set:
            question_set.set_status = "FAILED"
            db.commit()

        raise HTTPException(status_code=500, detail=f"질문 생성 실패: {e}") from e

def get_latest_completed_question_set(
    db: Session,
    resume_id: int,
) -> QuestionSet | None:
    return (
        db.query(QuestionSet)
        .filter(
            QuestionSet.resume_id == resume_id,
            QuestionSet.set_status == "COMPLETED",
        )
        .order_by(QuestionSet.set_id.desc())
        .first()
    )


def ensure_questions_generated_for_resume(
    db: Session,
    resume_id: int,
    target_count: int = 30,
    purpose: str = "DEFAULT",
    model: str = DEFAULT_MODEL,
) -> QuestionSet:
    latest_set = get_latest_completed_question_set(db, resume_id)

    if latest_set:
        selected_count = (
            db.query(Question)
            .filter(
                Question.set_id == latest_set.set_id,
                Question.qust_is_selected == 1,
            )
            .count()
        )

        if selected_count >= target_count:
            return latest_set

    return generate_questions_for_resume(
        db=db,
        resume_id=resume_id,
        target_count=target_count,
        purpose=purpose,
        model=model,
    )
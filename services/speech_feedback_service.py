from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.config import settings
from models.speech_feedback import SpeechFeedback
from sqlalchemy.orm import Session


@dataclass
class SpeechFeedbackResult:
    report_md: str
    coaching_md: str
    model: str


def _get_openai_client():
    api_key = settings.OPENAI_API_KEY or ""
    if not api_key.strip():
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise RuntimeError("openai package is not installed.") from exc
    return OpenAI(api_key=api_key)


def _build_messages(question_text: str, score_payload: dict[str, Any]) -> tuple[str, str]:
    compact_score = {
        "fluency_score": score_payload.get("fluency_score"),
        "clarity_score": score_payload.get("clarity_score"),
        "structure_score": score_payload.get("structure_score"),
        "length_score": score_payload.get("length_score"),
        "delivery_score": score_payload.get("delivery_score"),
        "content_score": score_payload.get("content_score"),
        "confidence_score": score_payload.get("confidence_score"),
        "metrics": score_payload.get("metrics", {}),
    }
    system_msg = (
        "You are a Korean interview speech coach focused only on delivery quality. "
        "You must evaluate only speaking/performance aspects from provided speech metrics. "
        "Never evaluate content relevance, technical correctness, or answer context. "
        "Do not mention specific technologies, concepts, or domain advice. "
        "Do not fabricate transcript quotes. "
        "Write all feedback in Korean using 해요체 only. "
        "Do not use 합니다체, 입니다체, or casual/plain speech. "
        "Output strict JSON only."
    )
    user_msg = (
        "면접 발화 지표만 근거로 아래 두 항목을 작성해 주세요.\n"
        "반드시 발화 성능(속도, 침묵, 반복, 명료성, 길이, 안정성)만 평가하세요.\n"
        "내용 적합성, 기술 정확성, 답변 맥락, 특정 기술/개념 언급은 금지합니다.\n"
        "1) 분석 리포트: 발화 강점/약점/원인 요약 (3~5개 bullet)\n"
        "2) 코칭 피드백: 다음 답변에서 바로 적용할 발화 훈련 지침 (3~5개 bullet)\n"
        "3) 모든 bullet은 한국어 해요체로만 작성하세요. 문장 끝은 '~해요', '~세요'처럼 쓰고, "
        "'~합니다', '~입니다', 반말은 쓰지 마세요.\n\n"
        f"지표: {json.dumps(compact_score, ensure_ascii=False)}\n\n"
        "JSON schema:\n"
        "{"
        "\"analysis_report\": [string, ...],"
        "\"coaching_feedback\": [string, ...]"
        "}"
    )
    return system_msg, user_msg


def _build_stream_messages(question_text: str, score_payload: dict[str, Any]) -> tuple[str, str]:
    compact_score = {
        "fluency_score": score_payload.get("fluency_score"),
        "clarity_score": score_payload.get("clarity_score"),
        "structure_score": score_payload.get("structure_score"),
        "length_score": score_payload.get("length_score"),
        "delivery_score": score_payload.get("delivery_score"),
        "content_score": score_payload.get("content_score"),
        "confidence_score": score_payload.get("confidence_score"),
        "metrics": score_payload.get("metrics", {}),
    }
    system_msg = (
        "You are a Korean interview speech coach focused only on delivery quality. "
        "Use only the provided speech metrics. "
        "Never evaluate content relevance, technical correctness, or answer context. "
        "Do not mention specific technologies, concepts, or domain advice. "
        "Do not fabricate transcript quotes. "
        "Write all feedback in Korean using 해요체 only. "
        "Do not use 합니다체, 입니다체, or casual/plain speech. "
        "Output Korean markdown only."
    )
    user_msg = (
        "면접 발화 지표만 근거로 발화 평가를 작성해 주세요.\n"
        "반드시 발화 성능(속도, 침묵, 반복, 명료성, 길이, 안정성)만 평가하세요.\n"
        "내용 적합성, 기술 정확성, 답변 맥락, 특정 기술/개념 언급은 금지합니다.\n"
        "출력은 헤더 없이 bullet 4~8개로만 작성하세요.\n"
        "모든 bullet은 한국어 해요체로만 작성하세요. 문장 끝은 '~해요', '~세요'처럼 쓰고, "
        "'~합니다', '~입니다', 반말은 쓰지 마세요.\n"
        "예: - 발화 속도는 안정적으로 유지돼요.\n\n"
        f"지표: {json.dumps(compact_score, ensure_ascii=False)}"
    )
    return system_msg, user_msg


def start_speech_feedback_stream(question_text: str, score_payload: dict[str, Any]):
    client = _get_openai_client()
    model = settings.OPENAI_MODEL
    sys_msg, user_msg = _build_stream_messages(question_text=question_text, score_payload=score_payload)
    stream = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ],
        stream=True,
    )
    return stream, model


def parse_stream_feedback_markdown(content: str, model: str) -> SpeechFeedbackResult:
    text = (content or "").strip()
    if not text:
        raise RuntimeError("LLM returned empty feedback.")

    report_title = "## 분석 리포트"
    coaching_title = "## 코칭 피드백"

    report_md = ""
    coaching_md = ""

    report_idx = text.find(report_title)
    coaching_idx = text.find(coaching_title)

    if report_idx != -1 and coaching_idx != -1 and report_idx < coaching_idx:
        report_md = text[report_idx + len(report_title) : coaching_idx].strip()
        coaching_md = text[coaching_idx + len(coaching_title) :].strip()
    else:
        # Single-section output mode: keep all feedback as report.
        report_md = text
        coaching_md = ""

    if not report_md.startswith("-"):
        report_lines = [line.strip() for line in report_md.splitlines() if line.strip()]
        report_md = "\n".join(f"- {line.lstrip('- ').strip()}" for line in report_lines[:5] if line.strip())

    if coaching_md and not coaching_md.startswith("-"):
        coaching_lines = [line.strip() for line in coaching_md.splitlines() if line.strip()]
        coaching_md = "\n".join(f"- {line.lstrip('- ').strip()}" for line in coaching_lines[:5] if line.strip())

    report_md = report_md.strip()
    coaching_md = coaching_md.strip()
    if not report_md:
        raise RuntimeError("LLM streamed feedback fields are empty.")

    return SpeechFeedbackResult(report_md=report_md, coaching_md=coaching_md, model=model)


def generate_speech_feedback(
    question_text: str,
    score_payload: dict[str, Any],
) -> SpeechFeedbackResult:
    client = _get_openai_client()
    model = settings.OPENAI_MODEL
    sys_msg, user_msg = _build_messages(question_text=question_text, score_payload=score_payload)

    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
    )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("LLM returned empty feedback.")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("LLM feedback is not valid JSON.") from exc

    report_lines = parsed.get("analysis_report", [])
    coaching_lines = parsed.get("coaching_feedback", [])
    if not isinstance(report_lines, list):
        report_lines = []
    if not isinstance(coaching_lines, list):
        coaching_lines = []

    report_clean = [str(x).strip() for x in report_lines if str(x).strip()]
    coaching_clean = [str(x).strip() for x in coaching_lines if str(x).strip()]

    if not report_clean or not coaching_clean:
        raise RuntimeError("LLM feedback fields are empty.")

    report_md = "\n".join(f"- {line}" for line in report_clean[:5])
    coaching_md = "\n".join(f"- {line}" for line in coaching_clean[:5])
    return SpeechFeedbackResult(report_md=report_md, coaching_md=coaching_md, model=model)


def upsert_speech_feedback(db: Session, sel_id: int, result: SpeechFeedbackResult) -> SpeechFeedback:
    row = db.query(SpeechFeedback).filter(SpeechFeedback.sel_id == sel_id).first()
    if row is None:
        row = SpeechFeedback(
            sel_id=sel_id,
            sfb_report_md=result.report_md,
            sfb_coaching_md=result.coaching_md,
            sfb_model=result.model,
        )
        db.add(row)
    else:
        row.sfb_report_md = result.report_md
        row.sfb_coaching_md = result.coaching_md
        row.sfb_model = result.model
    db.commit()
    db.refresh(row)
    return row


def get_speech_feedback(db: Session, sel_id: int) -> SpeechFeedback | None:
    return db.query(SpeechFeedback).filter(SpeechFeedback.sel_id == sel_id).first()

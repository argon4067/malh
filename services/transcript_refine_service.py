from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from core.config import settings
from models.transcript import Transcript
from models.transcript_refine import TranscriptRefine
from sqlalchemy.orm import Session


MIN_CONFIDENCE = 0.35
UNCERTAIN_CONFIDENCE_FLOOR = 0.55


@dataclass
class RefineResult:
    raw_text: str
    refined_text: str | None
    edit_log: dict[str, Any]
    confidence: int
    changed_ratio: float
    status: str
    reject_reason: str | None
    llm_model: str


def _get_openai_client():
    api_key = settings.OPENAI_API_KEY or ""
    if not api_key.strip():
        raise RuntimeError("OPENAI_API_KEY가 구성되지 않았습니다")
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise RuntimeError("openai package가 설치되지 않았습니다.") from exc
    return OpenAI(api_key=api_key)


def _extract_numbers(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", text)


def _changed_ratio(a: str, b: str) -> float:
    if not a and not b:
        return 0.0
    return 1.0 - SequenceMatcher(None, a, b).ratio()


def _normalize_surface(text: str) -> str:
    out = re.sub(r"[ \t]+", " ", (text or "").strip())
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    out = re.sub(r"([,.;:!?])([^\s])", r"\1 \2", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"\bcsv\b", "CSV", out, flags=re.IGNORECASE)
    out = re.sub(r"\bexcel\b", "Excel", out, flags=re.IGNORECASE)
    out = re.sub(r"\bdb\b", "DB", out, flags=re.IGNORECASE)
    out = re.sub(r"\bsql\b", "SQL", out, flags=re.IGNORECASE)
    out = re.sub(r"\bpython\b", "Python", out, flags=re.IGNORECASE)
    return out


def _build_messages(raw_text: str, question_text: str | None) -> tuple[str, str]:
    question = (question_text or "").strip() or "(question unavailable)"

    system_msg = (
        "You are a Korean interview answer reconstructor for evaluation. "
        "Your goal is to recover the intended meaning of the candidate's answer from noisy STT text. "
        "Use the interview question as primary context. "
        "Reconstruct the answer so that evaluators can judge whether the answer addressed the question. "
        "Do not invent new experience, projects, tools, metrics, or facts not supported by the transcript. "
        "Preserve numbers if present. "
        "If a span is too uncertain, keep it conservative rather than fabricating details. "
        "Return strict JSON only."
    )

    user_msg = (
        "Reconstruct the answer for evaluation.\n"
        f"QUESTION:\n{question}\n\n"
        f"RAW_STT:\n{raw_text}\n\n"
        "Return JSON with keys:\n"
        "{"
        "\"reconstructed_answer\": string,"
        "\"confidence\": number,"
        "\"uncertain\": boolean,"
        "\"answer_relevance_summary\": string,"
        "\"key_points\": [string]"
        "}"
    )
    return system_msg, user_msg


def _call_reconstructor(raw_text: str, question_text: str | None) -> tuple[dict[str, Any], str]:
    client = _get_openai_client()
    model = settings.OPENAI_MODEL
    sys_msg, user_msg = _build_messages(raw_text=raw_text, question_text=question_text)

    response = client.chat.completions.create(
        model=model,
        temperature=0.1,
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
    )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("LLM returned empty response.")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("LLM response is not valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("LLM response root must be JSON object.")

    return parsed, model


def refine_transcript_with_guardrails(raw_text: str, question_text: str | None = None) -> RefineResult:
    text = (raw_text or "").strip()
    if not text:
        raise RuntimeError("Transcript text is empty.")

    parsed, model = _call_reconstructor(raw_text=text, question_text=question_text)

    reconstructed = _normalize_surface(str(parsed.get("reconstructed_answer", "")).strip())
    conf = max(0.0, min(1.0, float(parsed.get("confidence", 0.5))))
    uncertain = bool(parsed.get("uncertain", False))

    relevance_summary = str(parsed.get("answer_relevance_summary", "")).strip()
    key_points = parsed.get("key_points", [])
    if not isinstance(key_points, list):
        key_points = []
    key_points = [str(x).strip() for x in key_points if str(x).strip()]

    if not reconstructed:
        return RefineResult(
            raw_text=text,
            refined_text=None,
            edit_log={
                "mode": "semantic_reconstruction_v2",
                "question_text": question_text,
                "answer_relevance_summary": relevance_summary,
                "key_points": key_points,
                "uncertain": uncertain,
            },
            confidence=int(conf * 100),
            changed_ratio=0.0,
            status="REJECTED",
            reject_reason="Reconstructed answer is empty.",
            llm_model=model,
        )

    if _extract_numbers(text) != _extract_numbers(reconstructed):
        return RefineResult(
            raw_text=text,
            refined_text=text,
            edit_log={
                "mode": "semantic_reconstruction_v2",
                "question_text": question_text,
                "answer_relevance_summary": relevance_summary,
                "key_points": key_points,
                "uncertain": uncertain,
            },
            confidence=int(conf * 100),
            changed_ratio=_changed_ratio(text, reconstructed),
            status="REJECTED",
            reject_reason="Numeric tokens changed.",
            llm_model=model,
        )

    ratio = _changed_ratio(text, reconstructed)

    if conf < MIN_CONFIDENCE:
        return RefineResult(
            raw_text=text,
            refined_text=text,
            edit_log={
                "mode": "semantic_reconstruction_v2",
                "question_text": question_text,
                "answer_relevance_summary": relevance_summary,
                "key_points": key_points,
                "uncertain": uncertain,
            },
            confidence=int(conf * 100),
            changed_ratio=ratio,
            status="REJECTED",
            reject_reason="Low confidence reconstruction.",
            llm_model=model,
        )

    if uncertain and conf < UNCERTAIN_CONFIDENCE_FLOOR:
        return RefineResult(
            raw_text=text,
            refined_text=text,
            edit_log={
                "mode": "semantic_reconstruction_v2",
                "question_text": question_text,
                "answer_relevance_summary": relevance_summary,
                "key_points": key_points,
                "uncertain": uncertain,
            },
            confidence=int(conf * 100),
            changed_ratio=ratio,
            status="REJECTED",
            reject_reason="Uncertain reconstruction.",
            llm_model=model,
        )

    return RefineResult(
        raw_text=text,
        refined_text=reconstructed,
        edit_log={
            "mode": "semantic_reconstruction_v2",
            "question_text": question_text,
            "answer_relevance_summary": relevance_summary,
            "key_points": key_points,
            "uncertain": uncertain,
        },
        confidence=int(conf * 100),
        changed_ratio=ratio,
        status="APPLIED",
        reject_reason=None,
        llm_model=model,
    )


def upsert_refine_result(db: Session, sel_id: int, result: RefineResult) -> TranscriptRefine:
    transcript = db.query(Transcript).filter(Transcript.sel_id == sel_id).first()
    if transcript is None:
        raise RuntimeError(f"Transcript not found for sel_id={sel_id}.")

    row = (
        db.query(TranscriptRefine)
        .filter(TranscriptRefine.transcript_id == transcript.transcript_id)
        .first()
    )
    if row is None:
        row = TranscriptRefine(transcript_id=transcript.transcript_id)
        db.add(row)

    row.r_raw_text = result.raw_text
    row.r_refined_text = result.refined_text
    row.r_edit_log = result.edit_log
    row.r_refine_confidence = result.confidence
    row.r_changed_ratio = int(round(result.changed_ratio * 100))
    row.r_status = result.status
    row.r_reject_reason = result.reject_reason
    row.r_llm_model = result.llm_model

    db.commit()
    db.refresh(row)
    return row

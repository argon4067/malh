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


REQUIRED_JSON_FIELDS = {
    "reconstructed_answer",
    "confidence",
    "uncertain",
    "answer_relevance_summary",
    "key_points",
}
MIN_CONFIDENCE = 0.35
UNCERTAIN_CONFIDENCE_FLOOR = 0.60
MAX_CHANGED_RATIO = 0.78
MAX_LENGTH_EXPANSION_RATIO = 1.65
MAX_NOVEL_TOKEN_RATIO = 0.72


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
    out = re.sub(r"\s+\.", ".", out)
    out = re.sub(r"\s+([,;:!?])", r"\1", out)
    out = re.sub(r"([,;:!?])([^\s])", r"\1 \2", out)
    return re.sub(r"\s{2,}", " ", out).strip()


def _tokenize_for_overlap(text: str) -> list[str]:
    return re.findall(r"[0-9A-Za-z가-힣_]+", (text or "").lower())


def _build_messages(raw_text: str, question_text: str | None) -> tuple[str, str]:
    question = (question_text or "").strip() or "(question unavailable)"

    system_msg = (
        "You are a grounded transcript reconstruction model for interview evaluation. "
        "Task: reconstruct what the speaker most likely said from noisy STT. "
        "This is reconstruction, not explanation, not answer generation. "
        "Use the question only for disambiguation of unclear wording. "
        "Never use the question as permission to add missing content. "
        "Do not add examples, procedures, definitions, implementation details, or extra claims not grounded in RAW_STT. "
        "If RAW_STT is short, incomplete, or vague, keep output short, incomplete, or vague. "
        "Preserve all numbers and concrete claims unless clearly recoverable from RAW_STT. "
        "Do not expand the answer into explanations, definitions, or additional details. However, you may correct obvious phonetic STT distortions when the intended wording is clearly supported by the question context and nearby words."
        "Return strict JSON only."
    )

    user_msg = (
        "Reconstruct the candidate answer.\n"
        f"QUESTION:\n{question}\n\n"
        f"RAW_STT:\n{raw_text}\n\n"
        "Return strict JSON with exactly these keys and no extra keys:\n"
        "{"
        "\"reconstructed_answer\": string,"
        "\"confidence\": number between 0 and 1,"
        "\"uncertain\": boolean,"
        "\"answer_relevance_summary\": short string,"
        "\"key_points\": [string]"
        "}"
    )
    return system_msg, user_msg


def _call_reconstructor(raw_text: str, question_text: str | None) -> tuple[dict[str, Any], str]:
    client = _get_openai_client()
    model = (settings.OPENAI_TRANSCRIPT_REFINE_MODEL or "").strip() or settings.OPENAI_MODEL
    sys_msg, user_msg = _build_messages(raw_text=raw_text, question_text=question_text)

    response = client.chat.completions.create(
        model=model,
        temperature=0.1,
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        timeout=settings.OPENAI_TRANSCRIPT_REFINE_TIMEOUT_SEC,
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


def _reject_result(
    text: str,
    model: str,
    question_text: str | None,
    conf: float,
    uncertain: bool,
    relevance_summary: str,
    key_points: list[str],
    ratio: float,
    reason: str,
    numeric_mismatch: bool = False,
    length_expansion_ratio: float | None = None,
    token_expansion_ratio: float | None = None,
    novel_token_ratio: float | None = None,
    raw_token_count: int | None = None,
    recon_token_count: int | None = None,
    added_token_count: int | None = None,
) -> RefineResult:
    return RefineResult(
        raw_text=text,
        refined_text=None,
        edit_log={
            "mode": "grounded_reconstruction_v3",
            "question_text": question_text,
            "answer_relevance_summary": relevance_summary,
            "key_points": key_points,
            "uncertain": uncertain,
            "numeric_mismatch": numeric_mismatch,
            "length_expansion_ratio": length_expansion_ratio,
            "token_expansion_ratio": token_expansion_ratio,
            "novel_token_ratio": novel_token_ratio,
            "raw_token_count": raw_token_count,
            "recon_token_count": recon_token_count,
            "added_token_count": added_token_count,
        },
        confidence=int(conf * 100),
        changed_ratio=ratio,
        status="REJECTED",
        reject_reason=reason,
        llm_model=model,
    )


def refine_transcript_with_guardrails(raw_text: str, question_text: str | None = None) -> RefineResult:
    text = (raw_text or "").strip()
    if not text:
        raise RuntimeError("Transcript text is empty.")

    parsed, model = _call_reconstructor(raw_text=text, question_text=question_text)

    if set(parsed.keys()) != REQUIRED_JSON_FIELDS:
        raise RuntimeError("LLM response must contain exactly the required JSON fields.")

    reconstructed_raw = parsed["reconstructed_answer"]
    confidence_raw = parsed["confidence"]
    uncertain_raw = parsed["uncertain"]
    relevance_raw = parsed["answer_relevance_summary"]
    key_points_raw = parsed["key_points"]

    if not isinstance(reconstructed_raw, str):
        raise RuntimeError("reconstructed_answer must be a string.")
    if not isinstance(confidence_raw, (int, float)) or isinstance(confidence_raw, bool):
        raise RuntimeError("confidence must be a float.")
    if not isinstance(uncertain_raw, bool):
        raise RuntimeError("uncertain must be a boolean.")
    if not isinstance(relevance_raw, str):
        raise RuntimeError("answer_relevance_summary must be a string.")
    if not isinstance(key_points_raw, list) or any(not isinstance(x, str) for x in key_points_raw):
        raise RuntimeError("key_points must be a string array.")

    conf = float(confidence_raw)
    if conf < 0.0 or conf > 1.0:
        raise RuntimeError("confidence must be between 0 and 1.")

    reconstructed = _normalize_surface(reconstructed_raw)
    uncertain = uncertain_raw
    relevance_summary = relevance_raw.strip()
    key_points = [x.strip() for x in key_points_raw if x.strip()]

    if not reconstructed:
        return _reject_result(
            text=text,
            model=model,
            question_text=question_text,
            conf=conf,
            uncertain=uncertain,
            relevance_summary=relevance_summary,
            key_points=key_points,
            ratio=0.0,
            reason="Reconstructed answer is empty.",
        )

    ratio = _changed_ratio(text, reconstructed)
    numeric_mismatch = _extract_numbers(text) != _extract_numbers(reconstructed)
    length_expansion_ratio = len(reconstructed) / max(1, len(text))
    raw_tokens = _tokenize_for_overlap(text)
    recon_tokens = _tokenize_for_overlap(reconstructed)
    raw_token_count = len(raw_tokens)
    recon_token_count = len(recon_tokens)
    token_expansion_ratio = recon_token_count / max(1, raw_token_count)
    raw_token_set = set(raw_tokens)
    novel_token_count = sum(1 for token in recon_tokens if token not in raw_token_set)
    novel_token_ratio = novel_token_count / max(1, len(recon_tokens))
    added_token_count = max(0, recon_token_count - raw_token_count)

    if conf < MIN_CONFIDENCE:
        return _reject_result(
            text=text,
            model=model,
            question_text=question_text,
            conf=conf,
            uncertain=uncertain,
            relevance_summary=relevance_summary,
            key_points=key_points,
            ratio=ratio,
            reason="Low confidence reconstruction.",
        )

    if uncertain and conf < UNCERTAIN_CONFIDENCE_FLOOR:
        return _reject_result(
            text=text,
            model=model,
            question_text=question_text,
            conf=conf,
            uncertain=uncertain,
            relevance_summary=relevance_summary,
            key_points=key_points,
            ratio=ratio,
            reason="Uncertain reconstruction.",
        )

    if numeric_mismatch:
        return _reject_result(
            text=text,
            model=model,
            question_text=question_text,
            conf=conf,
            uncertain=uncertain,
            relevance_summary=relevance_summary,
            key_points=key_points,
            ratio=ratio,
            reason="Numbers changed from raw STT.",
            numeric_mismatch=True,
        )

    if ratio > MAX_CHANGED_RATIO:
        return _reject_result(
            text=text,
            model=model,
            question_text=question_text,
            conf=conf,
            uncertain=uncertain,
            relevance_summary=relevance_summary,
            key_points=key_points,
            ratio=ratio,
            reason="Reconstruction changed too much from raw STT.",
            numeric_mismatch=False,
            length_expansion_ratio=length_expansion_ratio,
            novel_token_ratio=novel_token_ratio,
        )

    if length_expansion_ratio > MAX_LENGTH_EXPANSION_RATIO:
        return _reject_result(
            text=text,
            model=model,
            question_text=question_text,
            conf=conf,
            uncertain=uncertain,
            relevance_summary=relevance_summary,
            key_points=key_points,
            ratio=ratio,
            reason="Reconstruction expands too far beyond raw STT.",
            numeric_mismatch=False,
            length_expansion_ratio=length_expansion_ratio,
            novel_token_ratio=novel_token_ratio,
        )

    if raw_token_count <= 3 and len(text) <= 20 and token_expansion_ratio > 1.6:
        return _reject_result(
            text=text,
            model=model,
            question_text=question_text,
            conf=conf,
            uncertain=uncertain,
            relevance_summary=relevance_summary,
            key_points=key_points,
            ratio=ratio,
            reason="Short STT expanded too much.",
            numeric_mismatch=False,
            length_expansion_ratio=length_expansion_ratio,
            token_expansion_ratio=token_expansion_ratio,
            novel_token_ratio=novel_token_ratio,
            raw_token_count=raw_token_count,
            recon_token_count=recon_token_count,
            added_token_count=added_token_count,
        )

    if raw_token_count <= 3 and len(text) <= 20 and added_token_count >= 3:
        return _reject_result(
            text=text,
            model=model,
            question_text=question_text,
            conf=conf,
            uncertain=uncertain,
            relevance_summary=relevance_summary,
            key_points=key_points,
            ratio=ratio,
            reason="Too many added tokens for short STT.",
            numeric_mismatch=False,
            length_expansion_ratio=length_expansion_ratio,
            token_expansion_ratio=token_expansion_ratio,
            novel_token_ratio=novel_token_ratio,
            raw_token_count=raw_token_count,
            recon_token_count=recon_token_count,
            added_token_count=added_token_count,
        )

    if (
        novel_token_ratio > MAX_NOVEL_TOKEN_RATIO
        and token_expansion_ratio > 1.5
        and length_expansion_ratio > 1.55
    ):
        return _reject_result(
            text=text,
            model=model,
            question_text=question_text,
            conf=conf,
            uncertain=uncertain,
            relevance_summary=relevance_summary,
            key_points=key_points,
            ratio=ratio,
            reason="Too much unsupported new content in reconstruction.",
            numeric_mismatch=False,
            length_expansion_ratio=length_expansion_ratio,
            token_expansion_ratio=token_expansion_ratio,
            novel_token_ratio=novel_token_ratio,
            raw_token_count=raw_token_count,
            recon_token_count=recon_token_count,
            added_token_count=added_token_count,
        )

    return RefineResult(
        raw_text=text,
        refined_text=reconstructed,
        edit_log={
            "mode": "grounded_reconstruction_v3",
            "question_text": question_text,
            "answer_relevance_summary": relevance_summary,
            "key_points": key_points,
            "uncertain": uncertain,
            "numeric_mismatch": numeric_mismatch,
            "length_expansion_ratio": length_expansion_ratio,
            "token_expansion_ratio": token_expansion_ratio,
            "novel_token_ratio": novel_token_ratio,
            "raw_token_count": raw_token_count,
            "recon_token_count": recon_token_count,
            "added_token_count": added_token_count,
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

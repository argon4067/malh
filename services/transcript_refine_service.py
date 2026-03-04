from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from core.config import settings
from models.transcript_refine import TranscriptRefine
from sqlalchemy.orm import Session


MAX_CHANGED_RATIO = 0.15
MAX_CHANGED_RATIO_SEMANTIC = 0.10
MAX_CHANGED_SPAN_RATIO_SEMANTIC = 0.08
MAX_SEMANTIC_BREAKS = 3
LOW_CONFIDENCE_THRESHOLD = 0.45
MIN_SEMANTIC_CONFIDENCE = 0.55
MIN_ANOMALOUS_CONFIDENCE = 0.70

DOMAIN_RULES = {
    # frequent interview-domain STT confusions
    "\ub098\ubb34\uac00": "\ub098\ub204\uc5b4",  # 나무가 -> 나누어
    "\uba74\uc801": "\uba74\uc811",  # 면적 -> 면접
    "\ud14d\uc2a4\ub85c": "\ud14d\uc2a4\ud2b8\ub85c",  # 텍스로 -> 텍스트로
    "\uc9d1\uad50": "\uc9c0\ud45c",  # 집교 -> 지표
}


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
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise RuntimeError("openai package is not installed.") from exc
    return OpenAI(api_key=api_key)


def _build_messages(raw_text: str) -> tuple[str, str]:
    system_msg = (
        "You are a Korean transcript refiner. "
        "Only fix spacing/punctuation/obvious STT typos. "
        "Do not add new facts. "
        "Do not infer missing meaning except for semantic-break exception. "
        "Semantic-break exception: only when phrase is contextually impossible, "
        "you may replace one local word/phrase with the most plausible candidate. "
        "Keep edits local around the broken span. "
        "Never change numbers, dates, names, or technical terms unless clearly typo-level. "
        "If uncertain, keep original text. "
        "Output strict JSON."
    )
    user_msg = (
        "Refine this STT transcript with minimal edits.\n"
        f"RAW:\n{raw_text}\n\n"
        "Output JSON with keys:\n"
        "{"
        "\"refined_text\": string,"
        "\"changes\": [{\"type\": \"spacing|punctuation|typo|other\", \"before\": string, \"after\": string, \"reason\": string, \"confidence\": number}],"
        "\"overall_confidence\": number,"
        "\"semantic_breaks\": [{\"span_before\": string, \"span_after\": string, \"candidates\": [string], \"chosen\": string, \"reason\": string, \"confidence\": number}]"
        "}"
    )
    return system_msg, user_msg


def _extract_numbers(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", text)


def _changed_ratio(a: str, b: str) -> float:
    if not a and not b:
        return 0.0
    return 1.0 - SequenceMatcher(None, a, b).ratio()


def _changed_char_ratio(a: str, b: str) -> float:
    matcher = SequenceMatcher(None, a, b)
    changed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            changed += max(i2 - i1, j2 - j1)
    return changed / max(1, len(a))


def _local_edit_coverage(raw_text: str, refined_text: str, semantic_breaks: list[dict[str, Any]]) -> float:
    if not semantic_breaks:
        return 0.0
    windows: list[tuple[int, int]] = []
    text_len = len(raw_text)
    for sb in semantic_breaks:
        span_before = str(sb.get("span_before", "")).strip()
        if not span_before:
            continue
        idx = raw_text.find(span_before)
        if idx < 0:
            continue
        left = max(0, idx - 20)
        right = min(text_len, idx + len(span_before) + 20)
        windows.append((left, right))
    if not windows:
        return 0.0

    matcher = SequenceMatcher(None, raw_text, refined_text)
    changed_positions = set()
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag != "equal":
            if i1 == i2 and tag == "insert":
                # insertion has no raw span; anchor at insertion point
                changed_positions.add(max(0, i1 - 1))
            else:
                for p in range(i1, i2):
                    changed_positions.add(p)
    if not changed_positions:
        return 0.0

    inside = 0
    for p in changed_positions:
        if any(l <= p < r for l, r in windows):
            inside += 1
    outside = len(changed_positions) - inside
    return outside / max(1, len(raw_text))


def _validate_semantic_breaks(semantic_breaks: list[dict[str, Any]]) -> tuple[bool, str | None]:
    if len(semantic_breaks) > MAX_SEMANTIC_BREAKS:
        return False, f"Too many semantic breaks ({len(semantic_breaks)})."
    for idx, sb in enumerate(semantic_breaks):
        if not isinstance(sb, dict):
            return False, f"semantic_break[{idx}] is not an object."
        reason = str(sb.get("reason", "")).strip().lower()
        if reason not in {"semantic_break", "impossible", "anomalous"}:
            return False, f"semantic_break[{idx}] has invalid reason."
        candidates = sb.get("candidates", [])
        chosen = str(sb.get("chosen", "")).strip()
        if not isinstance(candidates, list) or not candidates:
            return False, f"semantic_break[{idx}] candidates missing."
        candidates_clean = [str(x).strip() for x in candidates if str(x).strip()]
        if not chosen:
            return False, f"semantic_break[{idx}] chosen missing."
        if chosen not in candidates_clean:
            return False, f"semantic_break[{idx}] chosen not in candidates."
        conf = float(sb.get("confidence", 0.0))
        if reason == "anomalous" and conf < MIN_ANOMALOUS_CONFIDENCE:
            return False, f"semantic_break[{idx}] anomalous confidence too low."
    return True, None


def _normalize_spaces(text: str) -> str:
    # keep punctuation/filler marks but remove repeated spaces/tabs
    return re.sub(r"[ \t]+", " ", text).strip()


def _apply_domain_rules(text: str) -> tuple[str, list[dict[str, Any]]]:
    refined = text
    logs: list[dict[str, Any]] = []
    for before, after in DOMAIN_RULES.items():
        if before in refined:
            refined = refined.replace(before, after)
            logs.append(
                {
                    "type": "rule",
                    "before": before,
                    "after": after,
                    "reason": "domain_rule",
                    "confidence": 0.99,
                }
            )
    return refined, logs


def _validate_candidate(
    raw_text: str,
    refined_text: str,
    semantic_breaks: list[dict[str, Any]],
    overall_conf: float,
) -> tuple[bool, str | None, float]:
    ratio = _changed_ratio(raw_text, refined_text)

    if semantic_breaks:
        sb_ok, sb_reason = _validate_semantic_breaks(semantic_breaks)
        if not sb_ok:
            return False, sb_reason, ratio
        if ratio > MAX_CHANGED_RATIO_SEMANTIC:
            return False, f"Changed ratio too high for semantic edit ({ratio:.3f}).", ratio
        changed_char_ratio = _changed_char_ratio(raw_text, refined_text)
        if changed_char_ratio > MAX_CHANGED_SPAN_RATIO_SEMANTIC:
            return False, f"Changed span ratio too high ({changed_char_ratio:.3f}).", ratio
        local_outside = _local_edit_coverage(raw_text, refined_text, semantic_breaks)
        if local_outside > 0.03:
            return False, f"Edits not localized enough (outside={local_outside:.3f}).", ratio
        min_semantic_conf = min(
            [float(sb.get("confidence", 0.0)) for sb in semantic_breaks] + [1.0]
        )
        if min_semantic_conf < MIN_SEMANTIC_CONFIDENCE:
            return False, "Low confidence semantic-break correction.", ratio
    else:
        if ratio > MAX_CHANGED_RATIO:
            return False, f"Changed ratio too high ({ratio:.3f}).", ratio

    if _extract_numbers(raw_text) != _extract_numbers(refined_text):
        return False, "Numeric tokens changed.", ratio

    if overall_conf < LOW_CONFIDENCE_THRESHOLD:
        return False, "Low overall confidence.", ratio

    return True, None, ratio


def refine_transcript_with_guardrails(raw_text: str) -> RefineResult:
    text = (raw_text or "").strip()
    if not text:
        raise RuntimeError("Transcript text is empty.")

    client = _get_openai_client()
    model = settings.OPENAI_MODEL
    sys_msg, user_msg = _build_messages(text)

    response = client.chat.completions.create(
        model=model,
        temperature=0.0,
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

    refined_text = str(parsed.get("refined_text", "")).strip()
    changes = parsed.get("changes", [])
    if not isinstance(changes, list):
        changes = []
    overall_conf = float(parsed.get("overall_confidence", 0.5))
    overall_conf = max(0.0, min(1.0, overall_conf))
    semantic_breaks = parsed.get("semantic_breaks", [])
    if not isinstance(semantic_breaks, list):
        semantic_breaks = []

    if not refined_text:
        return RefineResult(
            raw_text=text,
            refined_text=None,
            edit_log={"changes": changes, "semantic_breaks": semantic_breaks},
            confidence=int(overall_conf * 100),
            changed_ratio=0.0,
            status="REJECTED",
            reject_reason="Refined text is empty.",
            llm_model=model,
        )

    refined_text = _normalize_spaces(refined_text)
    refined_text, rule_logs = _apply_domain_rules(refined_text)

    ok, reason, ratio = _validate_candidate(
        raw_text=text,
        refined_text=refined_text,
        semantic_breaks=semantic_breaks,
        overall_conf=overall_conf,
    )
    if not ok:
        return RefineResult(
            raw_text=text,
            refined_text=text,  # fallback to raw when guardrail fails
            edit_log={"changes": changes, "semantic_breaks": semantic_breaks, "rule_changes": rule_logs},
            confidence=int(overall_conf * 100),
            changed_ratio=ratio,
            status="REJECTED",
            reject_reason=reason,
            llm_model=model,
        )

    return RefineResult(
        raw_text=text,
        refined_text=refined_text,
        edit_log={"changes": changes, "semantic_breaks": semantic_breaks, "rule_changes": rule_logs},
        confidence=int(overall_conf * 100),
        changed_ratio=ratio,
        status="APPLIED",
        reject_reason=None,
        llm_model=model,
    )


def upsert_refine_result(db: Session, sel_id: int, result: RefineResult) -> TranscriptRefine:
    row = db.query(TranscriptRefine).filter(TranscriptRefine.sel_id == sel_id).first()
    if row is None:
        row = TranscriptRefine(sel_id=sel_id)
        db.add(row)

    row.raw_text = result.raw_text
    row.refined_text = result.refined_text
    row.edit_log = result.edit_log
    row.refine_confidence = result.confidence
    row.changed_ratio = int(round(result.changed_ratio * 100))
    row.status = result.status
    row.reject_reason = result.reject_reason
    row.llm_model = result.llm_model

    db.commit()
    db.refresh(row)
    return row

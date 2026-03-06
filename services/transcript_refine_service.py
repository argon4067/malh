from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Literal

from core.config import settings
from models.transcript import Transcript
from models.transcript_refine import TranscriptRefine
from sqlalchemy.orm import Session


MAX_CHANGED_RATIO = 0.35
MAX_CHANGED_RATIO_SEMANTIC = 0.30
MAX_CHANGED_SPAN_RATIO_SEMANTIC = 0.25
MAX_SEMANTIC_BREAKS = 12
LOW_CONFIDENCE_THRESHOLD = 0.40
MIN_SEMANTIC_CONFIDENCE = 0.45
MIN_ANOMALOUS_CONFIDENCE = 0.60
MAX_OUTSIDE_EDIT_RATIO = 0.55

DOMAIN_RULES = {
    "\ub098\ubb34\uac00": "\ub098\ub204\uc5b4",
    "\uba74\uc801": "\uba74\uc811",
    "\ud14d\uc2a4\ub85c": "\ud14d\uc2a4\ud2b8\ub85c",
    "\uc9d1\uad50": "\uc9c0\ud45c",
    "\ub10c\ud30c\uc778": "\ub118\ud30c\uc774",
    "\ub10c\ud30c\uc77c": "\ub118\ud30c\uc774",
    "\ubcf4\uc548\uc801\uc73c\ub85c": "\ubcf4\uc644\uc801\uc73c\ub85c",
    "\ubcc4\ucd95\uce58": "\uacb0\uce21\uce58",
    "\uacb0\ucd95\uce58": "\uacb0\uce21\uce58",
    "\uacb0\uce21\ucc0c": "\uacb0\uce21\uce58",
    "\ub178\ub77d\uac12": "\ub204\ub77d\uac12",
    "\ubc31\ud130": "\ubca1\ud130",
    "\uc815\uc8fc": "\uc815\uaddc\ud654",
    "\ub300\uc120": "\uc5f0\uc0b0",
    "\uc9d1\uacc4\uacbd\uc555": "\uc9d1\uacc4 \uc791\uc5c5",
    "\ub300\uc6b0\ub0e5 \uc218\uce58 \uc5f0\uc0ac": "\ub300\uc6a9\ub7c9 \uc218\uce58 \uc5f0\uc0b0",
}

DATA_ANALYSIS_TERMS = {
    "\ud310\ub2e4\uc2a4",
    "\ub118\ud30c\uc774",
    "\ud3f4\ub77c\uc2a4",
    "\ud30c\uc774\uc36c",
    "r",
    "sql",
    "csv",
    "excel",
    "db",
    "\uacb0\uce21\uce58",
    "\uc790\ub8cc\ud615",
    "\ubcc0\ud658",
    "\uc9d1\uacc4",
    "\uc791\uc5c5",
    "\ub300\uc6a9\ub7c9",
    "\uc218\uce58",
    "\uc5f0\uc0b0",
    "\uc815\uaddc\ud654",
    "\uad6c\uac04",
    "\ubd84\ud560",
    "\ubc30\uc5f4",
    "\ub2e8\uc704",
    "\ubca1\ud130",
}

REGEX_RULES: list[tuple[str, str]] = [
    ("\ub118\\s*\ud30c\\s*\uc774", "\ub118\ud30c\uc774"),  # 넘 파 이 -> 넘파이
    ("\uc9d1\uacc4\\s*,?\\s*\uacbd\uc555", "\uc9d1\uacc4 \uc791\uc5c5"),  # 집계, 경압 -> 집계 작업
    ("\uacb0\uacfc\\s+\ub97c", "\uacb0\uacfc\ub97c"),  # 결과 를 -> 결과를
    ("\uc774\uc0c1\uce58\\s+\ub098", "\uc774\uc0c1\uce58\ub098"),  # 이상치 나 -> 이상치나
    ("\ubc18\\s*\ubcf5\ubb38", "\ubc18\ubcf5\ubb38"),  # 반 복문 -> 반복문
    ("\ub118\ud30c\uc774\\s*\uc740", "\ub118\ud30c\uc774\ub294"),  # 넘파이은 -> 넘파이는
    ("\ub118\ud30c\uc774\\s*\uc744", "\ub118\ud30c\uc774\ub97c"),  # 넘파이을 -> 넘파이를
    ("\uc815\ud655\ud558\uac8c\\s+\ud588\uc2b5\ub2c8\ub2e4", "\uc815\ud655\ud588\uc2b5\ub2c8\ub2e4"),  # 정확하게 했습니다 -> 정확했습니다
]


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


def _build_messages(raw_text: str, mode: Literal["minimal", "contextual"]) -> tuple[str, str]:
    if mode == "minimal":
        system_msg = (
            "You are a Korean transcript minimal refiner. "
            "Fix spacing, punctuation, and obvious STT typos only. "
            "Do not add new facts. Keep numbers/dates/names exactly. "
            "Prefer conservative edits."
        )
        user_msg = (
            "Refine this STT transcript conservatively.\n"
            f"RAW:\n{raw_text}\n\n"
            "Return strict JSON:\n"
            "{"
            "\"refined_text\": string,"
            "\"overall_confidence\": number,"
            "\"changes\": [{\"type\": \"spacing|punctuation|typo|other\", \"before\": string, \"after\": string, \"confidence\": number}]"
            "}"
        )
        return system_msg, user_msg

    term_hints = ", ".join(sorted(DATA_ANALYSIS_TERMS))
    system_msg = (
        "You are a Korean transcript contextual reconstructor. "
        "Goal: recover intended meaning from noisy STT text while preserving facts. "
        "Use local+global context and interview/data-analysis domain terms. "
        "You may repair broken technical terms when context is clear. "
        "Keep numbers/dates/names unchanged. "
        "If uncertain, keep original span or mark uncertainty. "
        f"Preferred domain term vocabulary: {term_hints}."
    )
    user_msg = (
        "Reconstruct this noisy STT transcript.\n"
        f"RAW:\n{raw_text}\n\n"
        "Return strict JSON:\n"
        "{"
        "\"refined_text\": string,"
        "\"overall_confidence\": number,"
        "\"semantic_edits\": [{\"before\": string, \"after\": string, \"reason\": string, \"confidence\": number}],"
        "\"uncertain_spans\": [{\"before\": string, \"after\": string, \"confidence\": number}]"
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


def _domain_term_hit_ratio(text: str) -> float:
    tokens = re.findall(r"[A-Za-z0-9\uac00-\ud7a3]+", text.lower())
    if not tokens:
        return 0.0
    hits = sum(1 for tok in tokens if tok in DATA_ANALYSIS_TERMS)
    return hits / len(tokens)


def _local_edit_coverage(raw_text: str, refined_text: str, semantic_breaks: list[dict[str, Any]]) -> float:
    if not semantic_breaks:
        return 0.0
    windows: list[tuple[int, int]] = []
    text_len = len(raw_text)
    for sb in semantic_breaks:
        span_before = str(sb.get("span_before") or sb.get("before") or "").strip()
        if not span_before:
            continue
        idx = raw_text.find(span_before)
        if idx < 0:
            continue
        left = max(0, idx - 30)
        right = min(text_len, idx + len(span_before) + 30)
        windows.append((left, right))
    if not windows:
        return 0.0

    matcher = SequenceMatcher(None, raw_text, refined_text)
    changed_positions = set()
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag != "equal":
            if i1 == i2 and tag == "insert":
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
    return outside / max(1, len(changed_positions))


def _validate_semantic_breaks(semantic_breaks: list[dict[str, Any]]) -> tuple[bool, str | None]:
    if len(semantic_breaks) > MAX_SEMANTIC_BREAKS:
        return False, f"Too many semantic breaks ({len(semantic_breaks)})."
    for idx, sb in enumerate(semantic_breaks):
        if not isinstance(sb, dict):
            return False, f"semantic_break[{idx}] is not an object."

        reason = str(sb.get("reason", "")).strip().lower()
        if reason and reason not in {
            "semantic_break",
            "impossible",
            "anomalous",
            "domain_reconstruction",
            "contextual_repair",
            "term_recovery",
            "typo_cluster",
        }:
            return False, f"semantic_break[{idx}] has invalid reason."

        candidates = sb.get("candidates", [])
        chosen = str(sb.get("chosen", "")).strip()
        if candidates:
            if not isinstance(candidates, list):
                return False, f"semantic_break[{idx}] candidates must be list."
            candidates_clean = [str(x).strip() for x in candidates if str(x).strip()]
            if chosen and chosen not in candidates_clean:
                return False, f"semantic_break[{idx}] chosen not in candidates."

        span_before = str(sb.get("span_before") or sb.get("before") or "").strip()
        span_after = str(sb.get("span_after") or sb.get("after") or "").strip()
        if not span_before or not span_after:
            return False, f"semantic_break[{idx}] before/after missing."

        conf = float(sb.get("confidence", 0.0))
        if reason == "anomalous" and conf < MIN_ANOMALOUS_CONFIDENCE:
            return False, f"semantic_break[{idx}] anomalous confidence too low."
    return True, None


def _normalize_spaces(text: str) -> str:
    out = re.sub(r"[ \t]+", " ", text).strip()
    # Remove spaces before punctuation and normalize around punctuation.
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    out = re.sub(r"([,.;:!?])([^\s])", r"\1 \2", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    # Normalize common English tech tokens casing.
    out = re.sub(r"\bcsv\b", "CSV", out, flags=re.IGNORECASE)
    out = re.sub(r"\bexcel\b", "Excel", out, flags=re.IGNORECASE)
    out = re.sub(r"\bdb\b", "DB", out, flags=re.IGNORECASE)
    return out


def _apply_regex_rules(text: str) -> tuple[str, list[dict[str, Any]]]:
    refined = text
    logs: list[dict[str, Any]] = []
    for pattern, replacement in REGEX_RULES:
        updated = re.sub(pattern, replacement, refined)
        if updated != refined:
            logs.append(
                {
                    "type": "rule_regex",
                    "before_pattern": pattern,
                    "after": replacement,
                    "reason": "domain_regex_rule",
                    "confidence": 0.98,
                }
            )
            refined = updated
    return refined, logs


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


def _postprocess_surface(text: str) -> tuple[str, list[dict[str, Any]]]:
    out = _normalize_spaces(text)
    out, regex_logs = _apply_regex_rules(out)
    out, rule_logs = _apply_domain_rules(out)
    out = _normalize_spaces(out)
    return out, regex_logs + rule_logs


def _normalize_semantic_breaks(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    items = parsed.get("semantic_breaks", [])
    if isinstance(items, list):
        for it in items:
            if not isinstance(it, dict):
                continue
            out.append(
                {
                    "span_before": str(it.get("span_before", "")).strip(),
                    "span_after": str(it.get("span_after", "")).strip(),
                    "candidates": it.get("candidates", []) if isinstance(it.get("candidates", []), list) else [],
                    "chosen": str(it.get("chosen", "")).strip(),
                    "reason": str(it.get("reason", "")).strip().lower(),
                    "confidence": float(it.get("confidence", 0.0)),
                }
            )

    edits = parsed.get("semantic_edits", [])
    if isinstance(edits, list):
        for it in edits:
            if not isinstance(it, dict):
                continue
            out.append(
                {
                    "span_before": str(it.get("before", "")).strip(),
                    "span_after": str(it.get("after", "")).strip(),
                    "candidates": [],
                    "chosen": "",
                    "reason": str(it.get("reason", "contextual_repair")).strip().lower(),
                    "confidence": float(it.get("confidence", 0.0)),
                }
            )

    return [x for x in out if x["span_before"] or x["span_after"]]


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
        if local_outside > MAX_OUTSIDE_EDIT_RATIO:
            return False, f"Edits not localized enough (outside={local_outside:.3f}).", ratio

        min_semantic_conf = min([float(sb.get("confidence", 0.0)) for sb in semantic_breaks] + [1.0])
        if min_semantic_conf < MIN_SEMANTIC_CONFIDENCE:
            return False, "Low confidence semantic-break correction.", ratio
    else:
        if ratio > MAX_CHANGED_RATIO:
            return False, f"Changed ratio too high ({ratio:.3f}).", ratio

    if _extract_numbers(raw_text) != _extract_numbers(refined_text):
        return False, "Numeric tokens changed.", ratio

    if overall_conf < LOW_CONFIDENCE_THRESHOLD:
        return False, "Low overall confidence.", ratio

    if ratio >= 0.15:
        raw_term_ratio = _domain_term_hit_ratio(raw_text)
        refined_term_ratio = _domain_term_hit_ratio(refined_text)
        if refined_term_ratio + 0.05 < raw_term_ratio:
            return False, "Domain plausibility degraded.", ratio

    return True, None, ratio


def _call_refiner_model(raw_text: str, mode: Literal["minimal", "contextual"]) -> dict[str, Any]:
    client = _get_openai_client()
    model = settings.OPENAI_MODEL
    sys_msg, user_msg = _build_messages(raw_text, mode=mode)

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
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM response root must be JSON object.")

    parsed["_model"] = model
    return parsed


def refine_transcript_with_guardrails(raw_text: str) -> RefineResult:
    text = (raw_text or "").strip()
    if not text:
        raise RuntimeError("Transcript text is empty.")

    minimal = _call_refiner_model(text, mode="minimal")
    minimal_text = str(minimal.get("refined_text", "")).strip() or text
    minimal_changes = minimal.get("changes", [])
    if not isinstance(minimal_changes, list):
        minimal_changes = []
    minimal_conf = max(0.0, min(1.0, float(minimal.get("overall_confidence", 0.5))))

    stage_text, rule_logs_1 = _postprocess_surface(minimal_text)

    contextual = _call_refiner_model(stage_text, mode="contextual")
    contextual_text = str(contextual.get("refined_text", "")).strip() or stage_text
    contextual_text, rule_logs_2 = _postprocess_surface(contextual_text)

    semantic_breaks = _normalize_semantic_breaks(contextual)
    uncertain_spans = contextual.get("uncertain_spans", [])
    if not isinstance(uncertain_spans, list):
        uncertain_spans = []

    contextual_conf = max(0.0, min(1.0, float(contextual.get("overall_confidence", 0.5))))
    overall_conf = max(minimal_conf, contextual_conf)
    model = str(contextual.get("_model", settings.OPENAI_MODEL))

    if not contextual_text:
        return RefineResult(
            raw_text=text,
            refined_text=None,
            edit_log={
                "minimal_changes": minimal_changes,
                "semantic_breaks": semantic_breaks,
                "uncertain_spans": uncertain_spans,
                "rule_changes": rule_logs_1 + rule_logs_2,
            },
            confidence=int(overall_conf * 100),
            changed_ratio=0.0,
            status="REJECTED",
            reject_reason="Refined text is empty.",
            llm_model=model,
        )

    ok, reason, ratio = _validate_candidate(
        raw_text=text,
        refined_text=contextual_text,
        semantic_breaks=semantic_breaks,
        overall_conf=overall_conf,
    )
    if not ok:
        ok_min, _reason_min, ratio_min = _validate_candidate(
            raw_text=text,
            refined_text=stage_text,
            semantic_breaks=[],
            overall_conf=minimal_conf,
        )
        if ok_min:
            return RefineResult(
                raw_text=text,
                refined_text=stage_text,
                edit_log={
                    "minimal_changes": minimal_changes,
                    "semantic_breaks": semantic_breaks,
                    "uncertain_spans": uncertain_spans,
                    "rule_changes": rule_logs_1,
                    "context_reject_reason": reason,
                },
                confidence=int(minimal_conf * 100),
                changed_ratio=ratio_min,
                status="APPLIED",
                reject_reason=None,
                llm_model=model,
            )

        return RefineResult(
            raw_text=text,
            refined_text=text,
            edit_log={
                "minimal_changes": minimal_changes,
                "semantic_breaks": semantic_breaks,
                "uncertain_spans": uncertain_spans,
                "rule_changes": rule_logs_1 + rule_logs_2,
            },
            confidence=int(overall_conf * 100),
            changed_ratio=ratio,
            status="REJECTED",
            reject_reason=reason,
            llm_model=model,
        )

    return RefineResult(
        raw_text=text,
        refined_text=contextual_text,
        edit_log={
            "minimal_changes": minimal_changes,
            "semantic_breaks": semantic_breaks,
            "uncertain_spans": uncertain_spans,
            "rule_changes": rule_logs_1 + rule_logs_2,
        },
        confidence=int(overall_conf * 100),
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

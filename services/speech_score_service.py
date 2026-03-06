from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from statistics import pstdev
from typing import Any

from models.speech_score_detail import SpeechScoreDetail
from models.speech_score_summary import SpeechScoreSummary
from sqlalchemy.orm import Session


FILLER_WORDS = {
    "\uc74c",  # 음
    "\uc5b4",  # 어
    "\uc800",  # 저
    "\uc57d\uac04",  # 약간
    "\ubb50\ub784\uae4c",  # 뭐랄까
    "\uadf8\ub7ec\ub2c8\uae4c",  # 그러니까
    "\uc0ac\uc2e4",  # 사실
}

CONNECTIVE_WORDS = {
    "\uadf8\ub9ac\uace0",  # 그리고
    "\uadf8\ub798\uc11c",  # 그래서
    "\ud558\uc9c0\ub9cc",  # 하지만
    "\ub610\ud55c",  # 또한
    "\uba3c\uc800",  # 먼저
    "\ub2e4\uc74c\uc73c\ub85c",  # 다음으로
    "\uacb0\uacfc\uc801\uc73c\ub85c",  # 결과적으로
    "\ub530\ub77c\uc11c",  # 따라서
    "\ubc18\uba74",  # 반면
    "\uc989",  # 즉
}

KOR_STOPWORDS = {
    "\uadf8", "\uc800", "\uc774", "\uac83", "\uc218", "\ub4f1", "\ubc0f",
    "\uc744", "\ub97c", "\uc740", "\ub294", "\uc5d0\uc11c", "\uc73c\ub85c",
    "\ud558\ub2e4", "\uc788\ub2e4", "\ub418\ub2e4", "\uc785\ub2c8\ub2e4", "\ud569\ub2c8\ub2e4",
    "\uad00\ub828", "\ub300\ud55c", "\ubb38\uc81c", "\uc9c0\uc6d0\uc790",
}

PARTICLE_SUFFIXES = (
    # Keep only suffixes with lower risk of over-stripping lexical stems.
    "\uc740", "\ub294", "\uac00", "\uc744", "\ub97c", "\uc5d0\uc11c",
    "\uc73c\ub85c", "\uc640", "\uacfc", "\ub3c4", "\ub9cc",
)


@dataclass
class SpeechScoreResult:
    fluency_score: float
    clarity_score: float
    structure_score: float
    length_score: float
    delivery_score: float
    content_score: float
    confidence_score: float
    metrics: dict[str, Any]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _target_band_score(value: float, low: float, high: float, hard_low: float, hard_high: float) -> float:
    if value <= hard_low or value >= hard_high:
        return 0.0
    if low <= value <= high:
        return 100.0
    if value < low:
        return _clamp((value - hard_low) / (low - hard_low) * 100.0, 0.0, 100.0)
    return _clamp((hard_high - value) / (hard_high - high) * 100.0, 0.0, 100.0)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9\uac00-\ud7a3]+", text.lower())


def _split_sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"[.!?。？！\n]+", text) if x.strip()]


def _normalize_surface_token(token: str) -> str:
    out = token
    for suffix in PARTICLE_SUFFIXES:
        if out.endswith(suffix) and len(out) > len(suffix) + 1:
            out = out[: -len(suffix)]
            break
    return out


def _normalize_topic_tokens(text: str) -> set[str]:
    toks = {_normalize_surface_token(t) for t in _tokenize(text)}
    return {t for t in toks if len(t) >= 2 and t not in KOR_STOPWORDS}


def _quality_ratio(text: str) -> float:
    # Transcript cleanliness proxy, not pronunciation quality.
    if not text:
        return 0.0
    total = len(text)
    good = len(re.findall(r"[A-Za-z0-9\uac00-\ud7a3\s.,!?%:;\"'()\[\]~…-]", text))
    return good / total if total else 0.0


def _count_fillers(text: str, tokens: list[str]) -> int:
    # Expanded boundary chars to reduce misses around punctuation/quotes/brackets.
    filler_pattern = r"(?:^|[\s,.:;!?\"'()\[\]~…\u2013\u2014-])(?:\uc74c+|\uc5b4+|\uc73c\uc74c+|\uc544+)(?:$|[\s,.:;!?\"'()\[\]~…\u2013\u2014-])"
    filler_pattern_count = len(re.findall(filler_pattern, text.lower()))
    token_count = sum(1 for t in tokens if t in FILLER_WORDS)
    return max(filler_pattern_count, token_count)


def _smooth_event_intensity(events_per_sentence: float, events_per_10sec: float) -> float:
    # Avoid hard clipping at 1.0 by using smooth saturation.
    # 0 -> 0, grows gradually and still differentiates high-event regions.
    combined = events_per_sentence * 0.7 + events_per_10sec * 0.3
    return 1.0 - math.exp(-combined)


def calculate_speech_scores(
    transcript_text: str,
    duration_sec: int,
    question_text: str | None = None,
) -> SpeechScoreResult:
    clean_text = (transcript_text or "").strip()
    tokens = _tokenize(clean_text)
    word_count = len(tokens)

    punct_sentences = _split_sentences(clean_text)
    if not punct_sentences and clean_text:
        punct_sentences = [clean_text]
    punctuation_sentence_count = len(punct_sentences)

    connective_count = sum(1 for t in tokens if t in CONNECTIVE_WORDS)
    # Reduce punctuation dependency without over-trusting connective repetition.
    connective_unit_est = (connective_count + 1) if word_count > 0 else 1
    if punctuation_sentence_count > 0:
        blended_units = round(punctuation_sentence_count * 0.75 + min(connective_unit_est, punctuation_sentence_count + 2) * 0.25)
        discourse_unit_count = max(1, blended_units)
    else:
        discourse_unit_count = max(1, min(connective_unit_est, 6))

    duration = max(1, int(duration_sec or 0))
    minutes = duration / 60.0
    wpm = word_count / minutes if minutes > 0 else 0.0

    filler_count = _count_fillers(clean_text, tokens)
    filler_events_per_sentence = filler_count / max(1, discourse_unit_count)
    filler_events_per_10sec = filler_count / max(1.0, duration / 10.0)
    filler_event_ratio = _clamp(_smooth_event_intensity(filler_events_per_sentence, filler_events_per_10sec), 0.0, 1.0)
    filler_ratio = filler_count / max(1, word_count)  # legacy compatibility

    repetition_count = sum(1 for idx in range(1, len(tokens)) if tokens[idx] == tokens[idx - 1])
    repetition_ratio = repetition_count / max(1, word_count - 1)

    sentence_lengths = [max(1, len(_tokenize(s))) for s in punct_sentences] if punct_sentences else [0]
    avg_sentence_len = sum(sentence_lengths) / max(1, punctuation_sentence_count)
    sentence_len_std = pstdev(sentence_lengths) if len(sentence_lengths) > 1 else 0.0

    # Use discourse-unit denominator for density metrics consistency.
    connective_density = connective_count / max(1, discourse_unit_count)

    response_topic_tokens = _normalize_topic_tokens(clean_text)
    question_topic_tokens = _normalize_topic_tokens(question_text or "")
    if question_topic_tokens:
        overlap_count = len(response_topic_tokens.intersection(question_topic_tokens))
        topic_overlap = overlap_count / len(question_topic_tokens)
    else:
        topic_overlap = 0.0

    # Estimated pause metrics (display-only proxies, not true pause measurement).
    est_speaking_time = word_count / 2.4
    silence_total_sec = _clamp(duration - est_speaking_time, 0.0, float(duration))
    pause_count = max(1, discourse_unit_count - 1)
    max_pause_sec = silence_total_sec / pause_count if pause_count > 0 else silence_total_sec
    pause_ratio = silence_total_sec / max(1.0, float(duration))
    speed_variation = sentence_len_std

    # Fluency axis.
    pace_score = _target_band_score(wpm, low=105.0, high=150.0, hard_low=60.0, hard_high=210.0)
    filler_score = _clamp(100.0 - filler_event_ratio * 125.0, 0.0, 100.0)
    repetition_score = _clamp(100.0 - repetition_ratio * 650.0, 0.0, 100.0)
    fluency_score = round(pace_score * 0.45 + filler_score * 0.3 + repetition_score * 0.25, 1)

    # Transcript-quality axis (legacy-named clarity for compatibility).
    transcript_cleanliness = _quality_ratio(clean_text)
    transcription_consistency = _clamp(
        0.62 + transcript_cleanliness * 0.35 - filler_event_ratio * 0.18 - repetition_ratio * 0.14,
        0.0,
        1.0,
    )
    clarity_score = round((transcription_consistency * 100.0) * 0.75 + (transcript_cleanliness * 100.0) * 0.25, 1)

    # Legacy-facing keys kept for template/API compatibility only.
    stt_accuracy = transcription_consistency
    avg_stt_confidence = _clamp(transcription_consistency - 0.015, 0.0, 1.0)
    pronunciation_clarity = _clamp(transcript_cleanliness - 0.03, 0.0, 1.0)
    articulation_ratio = _clamp(transcript_cleanliness + 0.02, 0.0, 1.0)
    volume_stability = _clamp(2.6 + pace_score / 100.0 * 0.9, 0.0, 4.0)
    clipping_ratio = _clamp((1.0 - transcript_cleanliness) * 0.02, 0.0, 0.02)

    # Structure axis.
    sentence_len_score = _target_band_score(avg_sentence_len, low=10.0, high=20.0, hard_low=5.0, hard_high=34.0)
    variation_score = _target_band_score(sentence_len_std, low=3.0, high=7.0, hard_low=0.5, hard_high=14.0)
    connective_score = _target_band_score(connective_density, low=0.35, high=1.0, hard_low=0.1, hard_high=2.0)
    structure_score = round(sentence_len_score * 0.45 + variation_score * 0.3 + connective_score * 0.25, 1)

    # Length axis (no sentence_len_score reuse to reduce duplicated effects).
    length_adequacy_score = _target_band_score(float(duration), low=70.0, high=110.0, hard_low=30.0, hard_high=180.0)
    word_count_score = _target_band_score(float(word_count), low=40.0, high=180.0, hard_low=10.0, hard_high=320.0)
    length_score = round(length_adequacy_score * 0.75 + word_count_score * 0.25, 1)

    # Content axis: keep relevance but avoid rewarding vocabulary size alone.
    numeric_density = len(re.findall(r"\d+", clean_text)) / max(1, discourse_unit_count)
    detail_score = _target_band_score(numeric_density, low=0.3, high=1.4, hard_low=0.05, hard_high=3.0)
    if question_topic_tokens:
        # Blend question-coverage and response-focus to reduce overlap-only bias.
        response_focus = len(response_topic_tokens.intersection(question_topic_tokens)) / max(
            1,
            len(response_topic_tokens),
        )
        relevance_score = round((topic_overlap * 100.0) * 0.7 + (response_focus * 100.0) * 0.3, 1)
    else:
        response_focus = 0.0
        relevance_score = 50.0
    topic_coverage = _target_band_score(float(len(response_topic_tokens)), low=8.0, high=22.0, hard_low=3.0, hard_high=45.0)
    gated_topic_coverage = topic_coverage * (0.5 + 0.5 * topic_overlap)
    content_score = round(relevance_score * 0.35 + connective_score * 0.25 + detail_score * 0.25 + gated_topic_coverage * 0.15, 1)

    delivery_score = round(fluency_score * 0.5 + clarity_score * 0.5, 1)
    confidence_score = round(
        _clamp(
            transcript_cleanliness * 100.0 * 0.42
            + transcription_consistency * 100.0 * 0.38
            + word_count_score * 0.20,
            0.0,
            100.0,
        ),
        1,
    )

    return SpeechScoreResult(
        fluency_score=fluency_score,
        clarity_score=clarity_score,
        structure_score=structure_score,
        length_score=length_score,
        delivery_score=delivery_score,
        content_score=content_score,
        confidence_score=confidence_score,
        metrics={
            "duration_sec": duration,
            "word_count": word_count,
            # Keep historical meaning: punctuation-based sentence count.
            "sentence_count": punctuation_sentence_count,
            "punctuation_sentence_count": punctuation_sentence_count,
            "discourse_unit_count": discourse_unit_count,
            "wpm": round(wpm, 1),
            "filler_count": filler_count,
            "filler_ratio": round(filler_ratio, 4),  # legacy
            "filler_events_per_sentence": round(filler_events_per_sentence, 4),
            "filler_events_per_10sec": round(filler_events_per_10sec, 4),
            "filler_event_ratio": round(filler_event_ratio, 4),
            "repetition_count": repetition_count,
            "repetition_ratio": round(repetition_ratio, 4),
            "avg_sentence_len": round(avg_sentence_len, 2),
            "sentence_len_std": round(sentence_len_std, 2),
            "connective_count": connective_count,
            "connective_density": round(connective_density, 4),
            "topic_overlap": round(topic_overlap, 4),
            "response_focus": round(response_focus, 4),
            "topic_token_count": len(response_topic_tokens),
            "topic_coverage": round(topic_coverage, 1),
            "gated_topic_coverage": round(gated_topic_coverage, 1),
            "relevance_score": relevance_score,
            "detail_score": round(detail_score, 1),
            # Legacy-facing keys (compatibility)
            "stt_accuracy": round(stt_accuracy, 4),
            "avg_stt_confidence": round(avg_stt_confidence, 4),
            "pronunciation_clarity": round(pronunciation_clarity, 4),
            "articulation_ratio": round(articulation_ratio, 4),
            "volume_stability": round(volume_stability, 2),
            "clipping_ratio": round(clipping_ratio, 4),
            # Estimated pause proxies (display-only)
            "silence_total_sec": round(silence_total_sec, 2),
            "max_pause_sec": round(max_pause_sec, 2),
            "pause_ratio": round(pause_ratio, 4),
            "pause_count": pause_count,
            "speed_variation": round(speed_variation, 2),
            "pause_estimated": True,
            # Band components
            "length_adequacy_score": round(length_adequacy_score, 1),
            "word_count_score": round(word_count_score, 1),
            "pace_score": round(pace_score, 1),
            "sentence_len_score": round(sentence_len_score, 1),
            # Explicit transcript-quality keys
            "transcript_cleanliness": round(transcript_cleanliness, 4),
            "transcription_consistency": round(transcription_consistency, 4),
            "legacy_metric_notice": "stt_accuracy/pronunciation_clarity/articulation_ratio/volume_stability are text-derived proxies.",
            # Aggregates
            "delivery_score": delivery_score,
            "content_score": content_score,
            "confidence_score": confidence_score,
        },
    )


def upsert_speech_summary(db: Session, sel_id: int, score: SpeechScoreResult) -> SpeechScoreSummary:
    row = db.query(SpeechScoreSummary).filter(SpeechScoreSummary.sel_id == sel_id).first()
    if row is None:
        row = SpeechScoreSummary(
            sel_id=sel_id,
            sss_fluency_score=score.fluency_score,
            sss_clarity_score=score.clarity_score,
            sss_structure_score=score.structure_score,
            sss_length_score=score.length_score,
        )
        db.add(row)
    else:
        row.sss_fluency_score = score.fluency_score
        row.sss_clarity_score = score.clarity_score
        row.sss_structure_score = score.structure_score
        row.sss_length_score = score.length_score
    db.commit()
    db.refresh(row)
    return row


def _score_to_payload_dict(score: SpeechScoreResult) -> dict[str, Any]:
    return {
        "fluency_score": score.fluency_score,
        "clarity_score": score.clarity_score,
        "structure_score": score.structure_score,
        "length_score": score.length_score,
        "delivery_score": score.delivery_score,
        "content_score": score.content_score,
        "confidence_score": score.confidence_score,
        "metrics": score.metrics,
    }


def upsert_speech_detail(db: Session, sel_id: int, score: SpeechScoreResult) -> SpeechScoreDetail:
    payload_json = json.dumps(_score_to_payload_dict(score), ensure_ascii=False)
    row = db.query(SpeechScoreDetail).filter(SpeechScoreDetail.sel_id == sel_id).first()
    if row is None:
        row = SpeechScoreDetail(sel_id=sel_id, ssd_payload_json=payload_json)
        db.add(row)
    else:
        row.ssd_payload_json = payload_json
    db.commit()
    db.refresh(row)
    return row


def get_speech_detail_payload(db: Session, sel_id: int) -> dict[str, Any] | None:
    row = db.query(SpeechScoreDetail).filter(SpeechScoreDetail.sel_id == sel_id).first()
    if row is None or not (row.ssd_payload_json or "").strip():
        return None
    try:
        payload = json.loads(row.ssd_payload_json)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None

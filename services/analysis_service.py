import json
import os
import statistics
from typing import Any
from core.config import settings

from openai import OpenAI
from sqlalchemy.orm import Session, joinedload

from models.answer_analysis import AnswerAnalysis
from models.interview_session import InterviewSession
from models.question import Question
from models.select_question import SelectQuestion
from models.transcript import Transcript
from services.prompt.analysis.answer_analysis_prompt import ANSWER_ANALYSIS_SYSTEM_PROMPT
from schemas.answer_analysis_schema import (
    AnswerAnalysisLLMResult,
    get_answer_analysis_response_format,
)
from services.weakness_service import get_session_weakness_top3

def _get_openai_client():
    api_key = settings.OPENAI_API_KEY or ""
    if not api_key.strip():
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise RuntimeError("openai package is not installed.") from exc
    return OpenAI(api_key=api_key)

client = _get_openai_client()


METRIC_LABEL_MAP = {
    "RELEVANCE": "질문 맥락 적합성",
    "COVERAGE": "답변 내용 충실도",
    "SPECIFICITY": "답변 구체성",
    "EVIDENCE": "근거 제시력",
    "CONSISTENCY": "이력서 정합성",
}

STATUS_PRIORITY = {
    "개선 확인": 4,
    "부분 개선": 3,
    "변화 미미": 2,
    "재보완 필요": 1,
}


def _limit_text(text: str | None, max_length: int = 12000) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_length:
        return text
    return text[:max_length] + "\n...(truncated)"


def _pick_answer_text(select_question: SelectQuestion) -> str:
    transcript = select_question.transcript
    if not transcript:
        raise ValueError("Transcript가 없습니다.")

    if transcript.transcript_text and transcript.transcript_text.strip():
        return transcript.transcript_text.strip()

    raise ValueError("분석할 답변 텍스트가 없습니다.")


def _pick_resume_text(select_question: SelectQuestion) -> str:
    interview_session = select_question.interview_session
    if not interview_session or not interview_session.resume:
        raise ValueError("Resume이 없습니다.")

    resume_text = interview_session.resume.resume_extracted_text
    if not resume_text or not resume_text.strip():
        raise ValueError("resume_extracted_text가 없습니다.")

    return resume_text.strip()


def _compute_overall_score(
    relevance_score: int,
    coverage_score: int,
    specificity_score: int,
    evidence_score: int,
    consistency_score: int,
) -> int:
    score = (
        relevance_score * 0.30
        + coverage_score * 0.25
        + specificity_score * 0.15
        + evidence_score * 0.15
        + consistency_score * 0.15
    )
    return round(score)


def _derive_weaknesses(result: AnswerAnalysisLLMResult) -> list[str]:
    threshold = 70
    weaknesses = []

    if result.relevance_score < threshold:
        weaknesses.append("RELEVANCE")
    if result.coverage_score < threshold:
        weaknesses.append("COVERAGE")
    if result.specificity_score < threshold:
        weaknesses.append("SPECIFICITY")
    if result.evidence_score < threshold:
        weaknesses.append("EVIDENCE")
    if result.consistency_score < threshold:
        weaknesses.append("CONSISTENCY")

    return weaknesses


def _build_user_prompt(
    question_text: str,
    question_evidence: list,
    answer_text: str,
    resume_text: str,
) -> str:
    return f"""
[질문]
{question_text}

[질문 근거]
{json.dumps(question_evidence, ensure_ascii=False)}

[답변]
{_limit_text(answer_text, 6000)}

[이력서 추출 텍스트]
{_limit_text(resume_text, 10000)}
""".strip()


def analyze_answer_by_sel_id(
    db: Session,
    sel_id: int,
    model: str = "gpt-4o-mini",
) -> AnswerAnalysis:
    select_question = (
        db.query(SelectQuestion)
        .options(
            joinedload(SelectQuestion.question),
            joinedload(SelectQuestion.transcript),
            joinedload(SelectQuestion.interview_session).joinedload(InterviewSession.resume),
            joinedload(SelectQuestion.answer_analysis),
        )
        .filter(SelectQuestion.sel_id == sel_id)
        .first()
    )

    if not select_question:
        raise ValueError(f"sel_id={sel_id} 질문을 찾을 수 없습니다.")
    if not select_question.question:
        raise ValueError("Question이 없습니다.")

    question_text = select_question.question.qust_question_text
    question_evidence = select_question.question.qust_evidence or []
    answer_text = _pick_answer_text(select_question)
    resume_text = _pick_resume_text(select_question)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": ANSWER_ANALYSIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_user_prompt(
                    question_text=question_text,
                    question_evidence=question_evidence,
                    answer_text=answer_text,
                    resume_text=resume_text,
                ),
            },
        ],
        response_format=get_answer_analysis_response_format(),
    )

    message = response.choices[0].message
    if getattr(message, "refusal", None):
        raise ValueError(f"LLM 분석이 거절되었습니다: {message.refusal}")

    content = message.content
    if not content:
        raise ValueError("LLM 응답이 비어 있습니다.")

    parsed = AnswerAnalysisLLMResult.model_validate(json.loads(content))

    overall_score = _compute_overall_score(
        relevance_score=parsed.relevance_score,
        coverage_score=parsed.coverage_score,
        specificity_score=parsed.specificity_score,
        evidence_score=parsed.evidence_score,
        consistency_score=parsed.consistency_score,
    )
    weaknesses = _derive_weaknesses(parsed)

    analysis = select_question.answer_analysis
    if analysis is None:
        analysis = AnswerAnalysis(sel_id=sel_id)
        db.add(analysis)

    analysis.anal_overall_score = overall_score
    analysis.anal_relevance_score = parsed.relevance_score
    analysis.anal_coverage_score = parsed.coverage_score
    analysis.anal_specificity_score = parsed.specificity_score
    analysis.anal_evidence_score = parsed.evidence_score
    analysis.anal_consistency_score = parsed.consistency_score
    analysis.anal_weakness = weaknesses

    analysis.anal_relevance_reason = parsed.relevance_reason
    analysis.anal_coverage_reason = parsed.coverage_reason
    analysis.anal_specificity_reason = parsed.specificity_reason
    analysis.anal_evidence_reason = parsed.evidence_reason
    analysis.anal_consistency_reason = parsed.consistency_reason
    analysis.anal_good_points = [item.model_dump() for item in parsed.good_points]
    analysis.anal_improvement_points = [item.model_dump() for item in parsed.improvement_points]
    analysis.anal_overall_comment = parsed.overall_comment
    analysis.anal_revised_answer = parsed.revised_answer
    analysis.anal_llm_model = model

    db.commit()
    db.refresh(analysis)
    return analysis

from models.speech_score_summary import SpeechScoreSummary

def get_session_score(db: Session, session_id: int) -> dict:
    """
    인터뷰 세션의 종합 점수를 계산합니다.
    1. 답변 내용 분석 (LLM) 점수 평균
    2. 발화 분석 (음성) 점수 평균 (유창성, 명료성, 구조, 길이 4종 평균)
    3. 종합 점수 (두 점수의 평균)
    """
    # 1. 답변 내용 분석 (LLM) 점수
    ans_scores = (
        db.query(AnswerAnalysis.anal_overall_score)
        .join(SelectQuestion, AnswerAnalysis.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == session_id)
        .all()
    )
    avg_ans = sum(s[0] for s in ans_scores) / len(ans_scores) if ans_scores else 0.0

    # 2. 발화 분석 (음성) 점수
    speech_rows = (
        db.query(
            SpeechScoreSummary.sss_fluency_score,
            SpeechScoreSummary.sss_clarity_score,
            SpeechScoreSummary.sss_structure_score,
            SpeechScoreSummary.sss_length_score
        )
        .join(SelectQuestion, SpeechScoreSummary.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == session_id)
        .all()
    )
    
    if speech_rows:
        total_speech_q_sum = 0.0
        for r in speech_rows:
            # 각 질문의 음성 점수 4종 평균
            q_speech_avg = (float(r[0]) + float(r[1]) + float(r[2]) + float(r[3])) / 4.0
            total_speech_q_sum += q_speech_avg
        avg_speech = total_speech_q_sum / len(speech_rows)
    else:
        avg_speech = 0.0

    # 3. 종합 점수 (두 점수 중 하나라도 있으면 평균, 아니면 있는 것 사용)
    if avg_ans > 0 and avg_speech > 0:
        overall = (avg_ans + avg_speech) / 2.0
    else:
        overall = avg_ans or avg_speech
    
    return {
        "overall": round(overall, 1),
        "answer": round(avg_ans, 1),
        "speech": round(avg_speech, 1)
    }

def _safe_strip(text: str | None) -> str:
    return " ".join((text or "").strip().split())


def _safe_json_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _extract_tracking_meta(question_evidence: Any) -> dict[str, Any]:
    evidences = _safe_json_list(question_evidence)
    for item in evidences:
        if isinstance(item, dict) and item.get("type") == "WEAKNESS_TRACKING":
            return item
    return {}


def _metric_score(analysis: AnswerAnalysis | None, metric: str) -> int | None:
    if not analysis:
        return None

    metric_score_map = {
        "RELEVANCE": analysis.anal_relevance_score,
        "COVERAGE": analysis.anal_coverage_score,
        "SPECIFICITY": analysis.anal_specificity_score,
        "EVIDENCE": analysis.anal_evidence_score,
        "CONSISTENCY": analysis.anal_consistency_score,
    }
    score = metric_score_map.get(metric)
    return int(score) if score is not None else None


def _metric_reason(analysis: AnswerAnalysis | None, metric: str) -> str:
    if not analysis:
        return ""

    metric_reason_map = {
        "RELEVANCE": analysis.anal_relevance_reason,
        "COVERAGE": analysis.anal_coverage_reason,
        "SPECIFICITY": analysis.anal_specificity_reason,
        "EVIDENCE": analysis.anal_evidence_reason,
        "CONSISTENCY": analysis.anal_consistency_reason,
    }
    return _safe_strip(metric_reason_map.get(metric))


def _avg(values: list[float | int | None]) -> float:
    cleaned = [float(v) for v in values if v is not None]
    if not cleaned:
        return 0.0
    return round(sum(cleaned) / len(cleaned), 1)


def _judge_delta(delta: float) -> str:
    if delta >= 10:
        return "개선 확인"
    if delta >= 5:
        return "부분 개선"
    if delta <= -5:
        return "재보완 필요"
    return "변화 미미"


def _score_desc(metric: str, score: float) -> str:
    label = METRIC_LABEL_MAP.get(metric, metric)
    if score >= 80:
        return f"{label}이 안정적으로 확보된 상태입니다."
    if score >= 65:
        return f"{label}은 개선되었지만 아직 다듬을 여지가 있습니다."
    return f"{label}은 여전히 보완이 필요한 상태입니다."


def _answer_summary(transcript: Transcript | None) -> str:
    if not transcript:
        return "답변 텍스트가 없습니다."

    text = ""
    if transcript.transcript_text and transcript.transcript_text.strip():
        text = transcript.transcript_text.strip()

    if not text:
        return "답변 텍스트가 없습니다."

    if len(text) <= 180:
        return text
    return text[:180].rstrip() + "..."


def _improvement_points(analysis: AnswerAnalysis | None) -> list[str]:
    if not analysis:
        return []

    points = _safe_json_list(analysis.anal_improvement_points)
    result = []
    for item in points:
        if isinstance(item, dict):
            detail = _safe_strip(item.get("detail"))
            if detail:
                result.append(detail)
    return result[:3]


def _load_session_rows(db: Session, session_id: int):
    return (
        db.query(SelectQuestion, Question, Transcript, AnswerAnalysis)
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .outerjoin(Transcript, Transcript.sel_id == SelectQuestion.sel_id)
        .outerjoin(AnswerAnalysis, AnswerAnalysis.sel_id == SelectQuestion.sel_id)
        .filter(SelectQuestion.inter_id == session_id)
        .order_by(SelectQuestion.sel_order_no.asc(), SelectQuestion.sel_id.asc())
        .all()
    )


def build_improvement_report(db: Session, session_id: int) -> dict[str, Any]:
    weakness_session = (
        db.query(InterviewSession)
        .options(joinedload(InterviewSession.question_set))
        .filter(InterviewSession.inter_id == session_id)
        .first()
    )
    if not weakness_session:
        raise ValueError("보강 세션을 찾을 수 없습니다.")
    if not weakness_session.question_set or weakness_session.question_set.set_purpose != "WEAKNESS":
        raise ValueError("보강 세션이 아닙니다.")
    if not weakness_session.source_inter_id:
        raise ValueError("원본 1차 세션 연결 정보가 없습니다.")

    source_session_id = int(weakness_session.source_inter_id)

    source_rows = _load_session_rows(db, source_session_id)
    weakness_rows = _load_session_rows(db, session_id)

    source_map = {int(sel.sel_id): (sel, question, transcript, analysis) for sel, question, transcript, analysis in source_rows}
    source_weakness_top3 = get_session_weakness_top3(db=db, session_id=source_session_id, top_k=3)

    metric_order = [item["metric"] for item in source_weakness_top3 if item.get("metric")]
    cards = []
    competency_changes = []
    question_items = []

    source_overall_scores = [analysis.anal_overall_score for _, _, _, analysis in source_rows if analysis]
    weakness_overall_scores = [analysis.anal_overall_score for _, _, _, analysis in weakness_rows if analysis]

    for metric in metric_order:
        related_weakness_rows = []
        related_source_rows = []

        for sel, question, transcript, analysis in weakness_rows:
            meta = _extract_tracking_meta(question.qust_evidence)
            if meta.get("weakness_metric") == metric:
                related_weakness_rows.append((sel, question, transcript, analysis, meta))
                source_sel_id = meta.get("source_sel_id")
                if source_sel_id and int(source_sel_id) in source_map:
                    related_source_rows.append(source_map[int(source_sel_id)])

        if not related_source_rows:
            related_source_rows = [
                row for row in source_rows
                if metric in ((row[3].anal_weakness or []) if row[3] else [])
            ]

        before_scores = [_metric_score(analysis, metric) for _, _, _, analysis in related_source_rows]
        after_scores = [_metric_score(analysis, metric) for _, _, _, analysis, _ in related_weakness_rows]

        before_avg = _avg(before_scores)
        after_avg = _avg(after_scores)
        delta = round(after_avg - before_avg, 1)
        status = _judge_delta(delta)

        source_reason = ""
        for _, _, _, analysis in related_source_rows:
            reason = _metric_reason(analysis, metric)
            if reason:
                source_reason = reason
                break

        after_reason = ""
        for _, _, _, analysis, _ in related_weakness_rows:
            reason = _metric_reason(analysis, metric)
            if reason:
                after_reason = reason
                break

        top3_item = next((item for item in source_weakness_top3 if item.get("metric") == metric), None)

        cards.append(
            {
                "metric": metric,
                "title": METRIC_LABEL_MAP.get(metric, metric),
                "before_score": before_avg,
                "after_score": after_avg,
                "delta": delta,
                "status": status,
                "before_state": source_reason or _score_desc(metric, before_avg),
                "after_state": after_reason or _score_desc(metric, after_avg),
                "tip": top3_item.get("tip") if top3_item else "",
                "summary": top3_item.get("summary") if top3_item else "",
            }
        )

        competency_changes.append(
            {
                "metric": metric,
                "label": METRIC_LABEL_MAP.get(metric, metric),
                "before_score": before_avg,
                "after_score": after_avg,
                "delta": delta,
            }
        )

        for sel, question, transcript, analysis, meta in related_weakness_rows:
            source_sel_id = meta.get("source_sel_id")
            source_bundle = source_map.get(int(source_sel_id)) if source_sel_id else None
            source_analysis = source_bundle[3] if source_bundle else None
            source_sel = source_bundle[0] if source_bundle else None

            before_score = _metric_score(source_analysis, metric) or 0
            after_score = _metric_score(analysis, metric) or 0
            row_delta = round(after_score - before_score, 1)

            question_items.append(
                {
                    "sel_id": int(sel.sel_id),
                    "sel_order_no": int(sel.sel_order_no),
                    "question_text": question.qust_question_text,
                    "target_metric": metric,
                    "target_label": METRIC_LABEL_MAP.get(metric, metric),
                    "source_sel_order_no": int(source_sel.sel_order_no) if source_sel else None,
                    "status": _judge_delta(row_delta),
                    "delta": row_delta,
                }
            )

    improved_count = sum(1 for card in cards if card["status"] == "개선 확인")
    partially_improved_count = sum(1 for card in cards if card["status"] == "부분 개선")
    tracked_count = len(cards)
    improvement_rate = int(round((improved_count / tracked_count) * 100)) if tracked_count else 0

    if improved_count >= max(1, tracked_count - 1):
        overall_status = "개선됨"
    elif improved_count + partially_improved_count > 0:
        overall_status = "부분 개선"
    elif any(card["status"] == "재보완 필요" for card in cards):
        overall_status = "악화 구간 존재"
    else:
        overall_status = "변화 미미"

    best_card = max(cards, key=lambda x: x["delta"], default=None)
    weakest_card = min(cards, key=lambda x: x["delta"], default=None)

    source_stability = statistics.pstdev(source_overall_scores) if len(source_overall_scores) >= 2 else 0
    weakness_stability = statistics.pstdev(weakness_overall_scores) if len(weakness_overall_scores) >= 2 else 0

    if weakness_stability + 3 < source_stability:
        stability_status = "높음"
    elif abs(weakness_stability - source_stability) <= 3:
        stability_status = "보통"
    else:
        stability_status = "낮음"

    action_guides = []
    for card in sorted(cards, key=lambda x: (STATUS_PRIORITY.get(x["status"], 0), x["delta"])):
        if card["status"] != "개선 확인":
            guide = card.get("tip") or f"{card['title']} 보완이 더 필요합니다."
            if guide not in action_guides:
                action_guides.append(guide)
    action_guides = action_guides[:3]

    return {
        "source_session_id": source_session_id,
        "weakness_session_id": session_id,
        "overview": {
            "overall_status": overall_status,
            "tracked_count": tracked_count,
            "improved_count": improved_count,
            "partially_improved_count": partially_improved_count,
            "improvement_rate": improvement_rate,
            "best_metric_label": best_card["title"] if best_card else "-",
            "best_metric_delta": best_card["delta"] if best_card else 0,
            "weakest_metric_label": weakest_card["title"] if weakest_card else "-",
            "weakest_metric_delta": weakest_card["delta"] if weakest_card else 0,
            "stability_status": stability_status,
        },
        "cards": cards,
        "competency_changes": competency_changes,
        "question_items": sorted(question_items, key=lambda x: x["sel_order_no"]),
        "action_guides": action_guides,
    }


def build_improvement_report_detail(
    db: Session,
    session_id: int,
    sel_id: int,
) -> dict[str, Any]:
    weakness_session = (
        db.query(InterviewSession)
        .options(joinedload(InterviewSession.question_set))
        .filter(InterviewSession.inter_id == session_id)
        .first()
    )
    if not weakness_session:
        raise ValueError("보강 세션을 찾을 수 없습니다.")
    if not weakness_session.question_set or weakness_session.question_set.set_purpose != "WEAKNESS":
        raise ValueError("보강 세션이 아닙니다.")
    if not weakness_session.source_inter_id:
        raise ValueError("원본 1차 세션 연결 정보가 없습니다.")

    weakness_row = (
        db.query(SelectQuestion, Question, Transcript, AnswerAnalysis)
        .join(Question, Question.qust_id == SelectQuestion.qust_id)
        .outerjoin(Transcript, Transcript.sel_id == SelectQuestion.sel_id)
        .outerjoin(AnswerAnalysis, AnswerAnalysis.sel_id == SelectQuestion.sel_id)
        .filter(
            SelectQuestion.inter_id == session_id,
            SelectQuestion.sel_id == sel_id,
        )
        .first()
    )
    if not weakness_row:
        raise ValueError("보강 질문을 찾을 수 없습니다.")

    weakness_sel, weakness_question, weakness_transcript, weakness_analysis = weakness_row
    tracking_meta = _extract_tracking_meta(weakness_question.qust_evidence)

    source_sel_id = tracking_meta.get("source_sel_id")
    source_row = None
    if source_sel_id:
        source_row = (
            db.query(SelectQuestion, Question, Transcript, AnswerAnalysis)
            .join(Question, Question.qust_id == SelectQuestion.qust_id)
            .outerjoin(Transcript, Transcript.sel_id == SelectQuestion.sel_id)
            .outerjoin(AnswerAnalysis, AnswerAnalysis.sel_id == SelectQuestion.sel_id)
            .filter(SelectQuestion.sel_id == int(source_sel_id))
            .first()
        )

    source_sel = source_question = source_transcript = source_analysis = None
    if source_row:
        source_sel, source_question, source_transcript, source_analysis = source_row

    target_metric = tracking_meta.get("weakness_metric", "")
    before_score = _metric_score(source_analysis, target_metric) or 0
    after_score = _metric_score(weakness_analysis, target_metric) or 0
    delta = round(after_score - before_score, 1)
    status = _judge_delta(delta)

    metric_rows = []
    for metric in ["RELEVANCE", "COVERAGE", "SPECIFICITY", "EVIDENCE", "CONSISTENCY"]:
        source_score = _metric_score(source_analysis, metric)
        weakness_score = _metric_score(weakness_analysis, metric)

        if source_score is None and weakness_score is None:
            continue

        source_score = source_score or 0
        weakness_score = weakness_score or 0
        metric_rows.append(
            {
                "label": METRIC_LABEL_MAP.get(metric, metric),
                "before_score": source_score,
                "after_score": weakness_score,
                "delta": round(weakness_score - source_score, 1),
            }
        )

    if delta >= 10:
        key_difference = "2차 답변에서 1차에 비해 핵심 약점이 눈에 띄게 보완되었습니다."
    elif delta >= 5:
        key_difference = "2차 답변에서 개선은 확인되지만 일부 보완 여지가 남아 있습니다."
    elif delta <= -5:
        key_difference = "2차 답변에서 1차보다 오히려 품질이 낮아진 구간이 확인됩니다."
    else:
        key_difference = "2차 답변은 1차와 비교해 큰 차이는 없으며 추가 연습이 필요합니다."

    remaining_points = _improvement_points(weakness_analysis)

    return {
        "source_session_id": weakness_session.source_inter_id,
        "weakness_session_id": session_id,
        "detail": {
            "sel_id": int(weakness_sel.sel_id),
            "sel_order_no": int(weakness_sel.sel_order_no),
            "question_text": weakness_question.qust_question_text,
            "target_metric": target_metric,
            "target_label": METRIC_LABEL_MAP.get(target_metric, target_metric),
            "target_title": tracking_meta.get("weakness_title", METRIC_LABEL_MAP.get(target_metric, target_metric)),
            "verification_purpose": tracking_meta.get("verification_purpose", ""),
            "source_sel_order_no": int(source_sel.sel_order_no) if source_sel else None,
            "source_question_text": source_question.qust_question_text if source_question else "",
            "before_score": before_score,
            "after_score": after_score,
            "delta": delta,
            "status": status,
            "before_answer_summary": _answer_summary(source_transcript),
            "after_answer_summary": _answer_summary(weakness_transcript),
            "before_reason": _metric_reason(source_analysis, target_metric),
            "after_reason": _metric_reason(weakness_analysis, target_metric),
            "key_difference": key_difference,
            "remaining_points": remaining_points,
            "metric_rows": metric_rows,
        },
    }

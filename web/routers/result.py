from fastapi import APIRouter, Depends, Request, status, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from core.database import get_db
from models.interview_session import InterviewSession
from models.select_question import SelectQuestion
from models.question import Question
from models.audio_recording import AudioRecording
from models.transcript import Transcript
from models.speech_score_summary import SpeechScoreSummary
from models.answer_analysis import AnswerAnalysis

from services.weakness_service import get_session_weakness_top3
from services.stt_service import run_stt_and_update
from services.speech_score_service import get_speech_detail_payload

from web.common import (
    templates, _get_resume_id_by_session, _safe_json_list, _safe_text
)

router = APIRouter()

@router.get("/interviews/{session_id}/results")
async def result_index(request: Request, session_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(
            SelectQuestion.sel_id, SelectQuestion.sel_order_no, SelectQuestion.sel_answer_duration_sec,
            Question.qust_question_text, AudioRecording.duration_sec.label("recorded_duration_sec"),
            AudioRecording.recording_id, SpeechScoreSummary.score_id.label("speech_score_id"),
            AnswerAnalysis.anal_id.label("answer_analysis_id"), AnswerAnalysis.anal_overall_score,
            AnswerAnalysis.anal_overall_comment, AnswerAnalysis.anal_revised_answer,
            AnswerAnalysis.anal_relevance_reason, AnswerAnalysis.anal_coverage_reason,
            AnswerAnalysis.anal_specificity_reason, AnswerAnalysis.anal_evidence_reason,
            AnswerAnalysis.anal_consistency_reason, AnswerAnalysis.anal_good_points,
            AnswerAnalysis.anal_improvement_points
        )
        .join(Question).outerjoin(AudioRecording).outerjoin(SpeechScoreSummary).outerjoin(AnswerAnalysis)
        .filter(SelectQuestion.inter_id == session_id).order_by(SelectQuestion.sel_order_no.asc()).all()
    )
    
    result_items = []
    for row in rows:
        context_feedback = None
        if row.answer_analysis_id:
            raw_good = _safe_json_list(row.anal_good_points)
            raw_imp = _safe_json_list(row.anal_improvement_points)
            context_feedback = {
                "overall_score": int(row.anal_overall_score or 0),
                "overall_comment": _safe_text(row.anal_overall_comment),
                "revised_answer": _safe_text(row.anal_revised_answer),
                "reason_rows": [
                    {"label": "질문 적합성", "text": _safe_text(row.anal_relevance_reason)},
                    {"label": "답변 충실도", "text": _safe_text(row.anal_coverage_reason)},
                    {"label": "구체성", "text": _safe_text(row.anal_specificity_reason)},
                    {"label": "근거 제시", "text": _safe_text(row.anal_evidence_reason)},
                    {"label": "이력서 정합성", "text": _safe_text(row.anal_consistency_reason)},
                ],
                "good_points": [{"title": _safe_text(i.get("title")), "detail": _safe_text(i.get("detail")), "metric": _safe_text(i.get("metric"))} for i in raw_good if isinstance(i, dict)],
                "improvement_points": [{"title": _safe_text(i.get("title")), "detail": _safe_text(i.get("detail")), "metric": _safe_text(i.get("metric"))} for i in raw_imp if isinstance(i, dict)],
            }
        result_items.append({
            "sel_id": row.sel_id, "sel_order_no": row.sel_order_no, "question_text": row.qust_question_text,
            "duration_sec": int(row.recorded_duration_sec or row.sel_answer_duration_sec or 0),
            "is_recorded": row.recording_id is not None, "speech_ready": row.speech_score_id is not None,
            "context_ready": row.answer_analysis_id is not None, "context_feedback": context_feedback
        })

    session = db.query(InterviewSession).filter(InterviewSession.inter_id == session_id).first()
    return templates.TemplateResponse("result/index.html", {
        "request": request, "session_id": session_id, "resume_id": _get_resume_id_by_session(db, session_id),
        "result_items": result_items, "weakness_top3": get_session_weakness_top3(db, session_id),
        "session_purpose": session.question_set.set_purpose if session and session.question_set else "DEFAULT"
    })

@router.get("/interviews/{session_id}/results/{sel_id}/stt")
async def result_analysis_stt(session_id: int, sel_id: int):
    return RedirectResponse(url=f"/interviews/{session_id}/results/{sel_id}/text", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

@router.get("/interviews/{session_id}/results/{sel_id}/text")
async def result_transcript(request: Request, session_id: int, sel_id: int, db: Session = Depends(get_db)):
    row = db.query(SelectQuestion.sel_order_no, Question.qust_question_text, AudioRecording.duration_sec, AudioRecording.file_path, Transcript.transcript_text, AnswerAnalysis).join(Question).outerjoin(AudioRecording).outerjoin(Transcript).outerjoin(AnswerAnalysis).filter(SelectQuestion.inter_id == session_id, SelectQuestion.sel_id == sel_id).first()
    if not row: raise HTTPException(status_code=404, detail="Not found")
    t_text = (row.transcript_text or "").strip()
    if not t_text and (row.file_path or "").strip():
        try: _, transcript = run_stt_and_update(db, session_id, sel_id); t_text = transcript.transcript_text
        except: pass
    effective_text = t_text or "전사 텍스트가 없습니다."
    return templates.TemplateResponse("result/transcript.html", {
        "request": request, "session_id": session_id, "sel_id": sel_id,
        "transcript_item": {
            "sel_order_no": row.sel_order_no, "question_text": row.qust_question_text, "duration_sec": int(row.duration_sec or 0),
            "transcript_text": effective_text, "audio_url": f"/storage/{row.file_path}" if row.file_path else None,
            "relevance_score": row.AnswerAnalysis.anal_relevance_score if row.AnswerAnalysis else 0,
            "coverage_score": row.AnswerAnalysis.anal_coverage_score if row.AnswerAnalysis else 0,
            "specificity_score": row.AnswerAnalysis.anal_specificity_score if row.AnswerAnalysis else 0,
            "evidence_score": row.AnswerAnalysis.anal_evidence_score if row.AnswerAnalysis else 0,
            "consistency_score": row.AnswerAnalysis.anal_consistency_score if row.AnswerAnalysis else 0,
            "speech_score": get_speech_detail_payload(db, sel_id)
        }
    })

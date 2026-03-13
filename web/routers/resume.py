from typing import List
import logging
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from core.database import get_db, SessionLocal, session_scope
from models.resume import Resume

from core.config import settings

router = APIRouter()

def _run_resume_pipeline_background(resume_id: int, model: str) -> None:
    logger.info("RESUME_PIPELINE_START resume_id=%s model=%s", resume_id, model)
    with session_scope() as db:
        try:
            analyze_saved_resume(db=db, resume_id=resume_id, model=model)
            resume = db.query(Resume).filter(Resume.resume_id == resume_id).first()
            if not resume: 
                return
            
            update_resume_status(db, resume, "QUESTION_GENERATING")
            ensure_questions_generated_for_resume(
                db=db, 
                resume_id=resume_id, 
                target_count=settings.RESUME_DEFAULT_QUESTION_COUNT, 
                purpose="DEFAULT", 
                model=model
            )
            
            resume = db.query(Resume).filter(Resume.resume_id == resume_id).first()
            if resume: 
                update_resume_status(db, resume, "DONE")
            
            logger.info("RESUME_PIPELINE_DONE resume_id=%s", resume_id)
        except Exception as e:
            logger.exception("RESUME_PIPELINE_FAIL resume_id=%s err=%s", resume_id, e)
            resume = db.query(Resume).filter(Resume.resume_id == resume_id).first()
            if resume:
                try: 
                    update_resume_status(db, resume, "FAILED", str(e))
                except Exception: 
                    pass

@router.get("/resumes")
async def resume_list(request: Request, db: Session = Depends(get_db)):
    user = _get_login_user(request, db)
    resumes = db.query(Resume).filter(Resume.user_id == user.user_id).order_by(Resume.resume_id.desc()).all()
    
    # 각 이력서별 연습 통계 추가
    for resume in resumes:
        # 연습 횟수 (완료된 세션 기준)
        practice_count = db.query(InterviewSession).filter(
            InterviewSession.resume_id == resume.resume_id,
            InterviewSession.inter_status == "DONE"
        ).count()
        
        # 마지막 연습 날짜
        last_session = db.query(InterviewSession).filter(
            InterviewSession.resume_id == resume.resume_id,
            InterviewSession.inter_status == "DONE"
        ).order_by(InterviewSession.inter_finished_at.desc()).first()
        
        # 객체에 속성 동적 추가
        resume.practice_count = practice_count
        resume.last_used_at = last_session.inter_finished_at if last_session and last_session.inter_finished_at else resume.resume_created_at

    return templates.TemplateResponse("resume/list.html", {
        "request": request, 
        "resume_id": None, 
        "default_model": DEFAULT_MODEL, 
        "resumes": resumes
    })

@router.post("/resumes")
async def create_resume(request: Request, model: str = Form(DEFAULT_MODEL), files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    user = _get_login_user(request, db)
    if not files: raise HTTPException(status_code=400, detail="업로드할 파일이 없습니다.")
    if len(files) > 1: raise HTTPException(status_code=400, detail="이력서는 한 번에 1개만 업로드할 수 있습니다.")
    file = files[0]
    try: data = await file.read()
    except Exception as e: raise HTTPException(status_code=400, detail=f"파일 읽기 실패: {e}") from e
    if not data: raise HTTPException(status_code=400, detail="빈 파일입니다.")
    resume = create_resume_record(db=db, user_id=user.user_id, original_filename=file.filename or "resume.pdf", data=data)
    return {"resume_id": resume.resume_id, "model": model}

@router.get("/resumes/{resume_id}/wait")
async def resume_wait(request: Request, resume_id: int):
    return templates.TemplateResponse("resume/wait.html", {"request": request, "resume_id": resume_id, "model": DEFAULT_MODEL})

@router.get("/resumes/{resume_id}")
async def resume_detail(request: Request, resume_id: int, db: Session = Depends(get_db)):
    user = _get_login_user(request, db)
    _get_owned_resume(db, user.user_id, resume_id)
    result = get_resume_analysis_result(db, resume_id)

    # 연습 기록 및 점수 데이터 조회
    sessions = (
        db.query(InterviewSession)
        .filter(InterviewSession.resume_id == resume_id, InterviewSession.inter_status == "DONE")
        .order_by(InterviewSession.inter_finished_at.desc())
        .all()
    )

    practice_history = []
    score_history = []
    for s in sessions:
        score_data = get_session_score(db, s.inter_id)
        hist_item = {
            "session_id": s.inter_id,
            "date": s.inter_finished_at.strftime("%Y-%m-%d") if s.inter_finished_at else "-",
            "score": score_data["overall"],
            "answer_score": score_data["answer"],
            "speech_score": score_data["speech"]
        }
        practice_history.append(hist_item)
        score_history.append(hist_item)

    # 그래프용은 과거 -> 현재 순서로 (최대 최근 10개)
    score_history = score_history[:10]
    score_history.reverse()

    # 최근 세션의 약점 분석
    weaknesses = []
    if sessions:
        latest_session_id = sessions[0].inter_id
        weaknesses = get_session_weakness_top3(db, latest_session_id)

    return templates.TemplateResponse("resume/detail.html", {
        "request": request,
        "resume_id": resume_id,
        "resume": result["resume"],
        "classification": result["classification"],
        "keywords": result["keywords"],
        "structured": result["structured"],
        "practice_history": practice_history,
        "weaknesses": weaknesses,
        "score_history": score_history
    })

@router.get("/resumes/{resume_id}/feedback")
async def resume_feedback(request: Request, resume_id: int, db: Session = Depends(get_db)):
    user = _get_login_user(request, db)
    _get_owned_resume(db, user.user_id, resume_id)
    return templates.TemplateResponse("resume/feedback.html", {"request": request, "resume_id": resume_id, "session_id": _get_latest_session_id_by_resume(db, resume_id)})

@router.post("/resumes/{resume_id}/analyze")
@router.post("/resumes/{resume_id}/analyze/start")
async def start_resume_analysis(request: Request, resume_id: int, background_tasks: BackgroundTasks, model: str = Form(DEFAULT_MODEL), db: Session = Depends(get_db)):
    user = _get_login_user(request, db)
    resume = _get_owned_resume(db, user.user_id, resume_id)
    if resume.resume_status == "DONE":
        return {"ok": True, "resume_id": resume_id, "status": resume.resume_status, "message": "이미 분석 완료된 이력서입니다."}
    if resume.resume_status in RUNNING_RESUME_STATUSES:
        return {"ok": True, "resume_id": resume_id, "status": resume.resume_status, "message": "이미 분석이 진행 중입니다."}
    update_resume_status(db, resume, "CLASSIFYING")
    background_tasks.add_task(_run_resume_pipeline_background, resume_id, model)
    return {"ok": True, "resume_id": resume_id, "status": "CLASSIFYING", "message": "분석이 시작되었습니다."}

@router.post("/resumes/{resume_id}/delete")
async def remove_resume(request: Request, resume_id: int, db: Session = Depends(get_db)):
    user = _get_login_user(request, db)
    _get_owned_resume(db, user.user_id, resume_id)
    delete_resume(db=db, resume_id=resume_id)
    return RedirectResponse(url="/resumes", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/resumes/{resume_id}/status")
async def get_resume_status(request: Request, resume_id: int, db: Session = Depends(get_db)):
    user = _get_login_user(request, db)
    resume = _get_owned_resume(db, user.user_id, resume_id)
    return {"resume_id": resume.resume_id, "status": resume.resume_status, "progress": RESUME_PROGRESS_MAP.get(resume.resume_status, 0), "error_message": resume.resume_error_message, "detail_url": f"/resumes/{resume.resume_id}"}

@router.post("/questions/generate/{resume_id}")
async def generate_questions(request: Request, resume_id: int, db: Session = Depends(get_db)):
    user = _get_login_user(request, db)
    _get_owned_resume(db, user.user_id, resume_id)
    try:
        question_set = generate_questions_for_resume(
            db=db, 
            resume_id=resume_id, 
            target_count=settings.RESUME_DEFAULT_QUESTION_COUNT, 
            purpose="DEFAULT"
        )
        selected_questions = db.query(Question).filter(Question.set_id == question_set.set_id, Question.qust_is_selected == 1).order_by(Question.qust_id.asc()).all()
        return {"message": "질문 생성이 완료되었습니다.", "set_id": question_set.set_id, "set_status": question_set.set_status, "set_attempt": question_set.set_attempt, "selected_count": len(selected_questions), "questions": [{"qust_id": q.qust_id, "category": q.qust_category, "difficulty": q.qust_difficulty, "question_text": q.qust_question_text, "evidence": q.qust_evidence} for q in selected_questions]}
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=f"질문 생성 실패: {e}") from e

@router.get("/questions/set/{set_id}")
async def get_question_set_result(request: Request, set_id: int, db: Session = Depends(get_db)):
    user = _get_login_user(request, db)
    question_set = db.query(QuestionSet).filter(QuestionSet.set_id == set_id).first()
    if not question_set: raise HTTPException(status_code=404, detail="질문 세트를 찾을 수 없습니다.")
    _get_owned_resume(db, user.user_id, question_set.resume_id)
    selected_questions = db.query(Question).filter(Question.set_id == set_id, Question.qust_is_selected == 1).order_by(Question.qust_id.asc()).all()
    rejected_questions = db.query(Question, QuestionFilterResult).join(QuestionFilterResult, Question.qust_id == QuestionFilterResult.qust_id).filter(Question.set_id == set_id, Question.qust_is_selected == 0).order_by(Question.qust_id.asc()).all()
    return {"set_id": question_set.set_id, "resume_id": question_set.resume_id, "set_status": question_set.set_status, "set_attempt": question_set.set_attempt, "set_purpose": question_set.set_purpose, "selected_count": len(selected_questions), "rejected_count": len(rejected_questions), "selected_questions": [{"qust_id": q.qust_id, "category": q.qust_category, "difficulty": q.qust_difficulty, "question_text": q.qust_question_text, "evidence": q.qust_evidence} for q in selected_questions], "rejected_questions": [{"qust_id": q.qust_id, "category": q.qust_category, "difficulty": q.qust_difficulty, "question_text": q.qust_question_text, "evidence": q.qust_evidence, "reasons": f.qfr_reasons, "duplicate_similarity": float(f.qfr_duplicate_similarity) if f.qfr_duplicate_similarity is not None else None} for q, f in rejected_questions]}

@router.post("/resumes/{resume_id}/start-practice")
async def start_practice(request: Request, resume_id: int, db: Session = Depends(get_db)):
    user = _get_login_user(request, db)
    _get_owned_resume(db, user.user_id, resume_id)
    question_set = get_latest_completed_question_set(db, resume_id)
    if not question_set: raise HTTPException(status_code=409, detail="생성된 질문 세트가 없습니다. 먼저 이력서 분석을 완료해주세요.")
    
    practice_count = settings.INTERVIEW_PRACTICE_QUESTION_COUNT
    selected_questions = db.query(Question).filter(Question.set_id == question_set.set_id, Question.qust_is_selected == 1).order_by(func.rand()).limit(practice_count).all()
    
    if len(selected_questions) < practice_count: 
        raise HTTPException(status_code=409, detail=f"출제 가능한 질문이 {practice_count}개 미만입니다.")
    try:
        interview_session = InterviewSession(user_id=user.user_id, resume_id=resume_id, set_id=question_set.set_id, inter_status="IN_PROGRESS")
        db.add(interview_session); db.flush()
        for idx, question in enumerate(selected_questions, start=1):
            db.add(SelectQuestion(inter_id=interview_session.inter_id, qust_id=question.qust_id, sel_order_no=idx))
        db.commit(); db.refresh(interview_session)
        return {"ok": True, "session_id": interview_session.inter_id, "resume_id": resume_id, "set_id": question_set.set_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"연습 세션 생성 실패: {e}") from e

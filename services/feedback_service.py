from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from core.database import get_db
from models.resume import Resume
from models.user import User

router = APIRouter(
    prefix="/feedback",
    tags=["Feedback"]
)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def get_current_user_from_cookie(request: Request, db: Session = Depends(get_db)):
    username = request.cookies.get("login_user")
    
    if not username:
        return None
        
    user = db.query(User).filter(
        User.user_username == username,
        User.user_status == 1
    ).first()
    
    return user

@router.get("", response_class=HTMLResponse)
def get_feedback_page(
    request: Request, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user_from_cookie)
):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)

    resumes = (
        db.query(Resume)
        .filter(Resume.user_id == current_user.user_id)
        .order_by(Resume.resume_created_at.desc())
        .all()
    )
    
    # 주의: HTML 파일 위치가 templates/feedback.html 이면 "feedback.html", 
    # templates/resume/feedback.html 이면 "resume/feedback.html" 로 맞춰주세요.
    return templates.TemplateResponse(
        "resume/feedback.html",
        {
            "request": request,
            "resumes": resumes
        }
    )
import re
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from starlette import status
from pydantic import BaseModel


from sqlalchemy.orm import Session
from core.database import get_db
from models.user import User

router = APIRouter()

templates = Jinja2Templates(directory="templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ID_REGEX = r"^[A-Za-z0-9]{6,20}$"
PW_REGEX = r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&]).{8,}$"

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


# 회원가입
@router.get("/auth/signup")
def signup_page(request: Request):
    return templates.TemplateResponse("auth/signup.html", {"request": request})

@router.post("/auth/signup")
def signup(
    request: Request,
    userId: str = Form(...),
    userPw: str = Form(...),
    userPwConfirm: str = Form(...),
    db: Session = Depends(get_db)
):
    if not re.match(ID_REGEX, userId):
        return templates.TemplateResponse("auth/signup.html", {"request": request, "error": "아이디 형식이 올바르지 않습니다."})
    if not re.match(PW_REGEX, userPw):
        return templates.TemplateResponse("auth/signup.html", {"request": request, "error": "비밀번호 형식이 올바르지 않습니다."})
    if userPw != userPwConfirm:
        return templates.TemplateResponse("auth/signup.html", {"request": request, "error": "비밀번호가 일치하지 않습니다."})

    user = db.query(User).filter(User.user_username == userId).first()
    if user:
        error_msg = "탈퇴처리된 계정입니다." if user.user_status == 0 else "이미 존재하는 아이디입니다."
        return templates.TemplateResponse("auth/signup.html", {"request": request, "error": error_msg})

    new_user = User(user_username=userId, user_pw=hash_password(userPw))
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)


# 로그인
@router.get("/auth/login")
def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})

@router.post("/auth/login")
def login(
    request: Request,
    userId: str = Form(...),
    userPw: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.user_username == userId).first()
    if not user or not verify_password(userPw, user.user_pw):
        return templates.TemplateResponse("auth/login.html", {"request": request, "error": "아이디 또는 비밀번호가 일치하지 않습니다."})
    if user.user_status == 0:
        return templates.TemplateResponse("auth/login.html", {"request": request, "error": "탈퇴 처리된 계정입니다."})

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    

    response.set_cookie(
        key="login_user", 
        value=user.user_username, 
        path="/", 
        httponly=True,
        max_age=3600,
        samesite="lax"
    )
    return response


# 로그아웃
@router.get("/auth/logout")
def logout():
    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="login_user", path="/")
    return response

# 비밀번호 변경 및 회원 탈퇴
@router.post("/auth/change-password")
def change_password(
    request: Request,
    data: PasswordChangeRequest,
    db: Session = Depends(get_db)
):
    user_id = request.cookies.get("login_user")
    
    if not user_id:
        return JSONResponse(content={"success": False, "detail": "로그인이 필요합니다."})
        
    if not re.match(PW_REGEX, data.new_password):
        return JSONResponse(content={"success": False, "detail": "비밀번호 형식이 올바르지 않습니다."})
        
    user = db.query(User).filter(User.user_username == user_id).first()
    if not user:
        return JSONResponse(content={"success": False, "detail": "사용자를 찾을 수 없습니다."})

    if not verify_password(data.current_password, user.user_pw):
        return JSONResponse(content={"success": False, "detail": "현재 비밀번호가 틀립니다."})
        
    if verify_password(data.new_password, user.user_pw):
        return JSONResponse(content={"success": False, "detail": "기존 비밀번호와 동일합니다. 다른 비밀번호를 사용해 주세요."})
        
    user.user_pw = hash_password(data.new_password)
    db.commit()
    
    response = JSONResponse(content={"success": True, "message": "비밀번호가 성공적으로 변경되었습니다. 다시 로그인 해주세요"})
    response.delete_cookie(key="login_user", path="/")
    return response

@router.post("/auth/withdraw")
def withdraw_user(
    request: Request,
    db: Session = Depends(get_db)
):
    user_id = request.cookies.get("login_user")
    user = db.query(User).filter(User.user_username == user_id).first()
        
    user.user_status = 0
    db.commit()
    
    response = JSONResponse(content={"message": "회원 탈퇴가 완료되었습니다."})
    response.delete_cookie(key="login_user", path="/")
    return response


@router.get("/resume/feedback")
def feedback_page(request: Request, db: Session = Depends(get_db)):

    resumes = [] 
    return templates.TemplateResponse("feedback.html", {"request": request, "resumes": resumes})
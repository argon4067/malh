import re
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from starlette import status

# SQLAlchemy 세션 및 모델 임포트
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

# =====================================================
# 회원가입 페이지 (GET)
# =====================================================
@router.get("/auth/signup")
def signup_page(request: Request):
    return templates.TemplateResponse("auth/signup.html", {"request": request})

# =====================================================
# 회원가입 처리 (POST)
# =====================================================
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

    existing_user = db.query(User).filter(User.user_username == userId).first()
    if existing_user:
        return templates.TemplateResponse("auth/signup.html", {"request": request, "error": "이미 존재하는 아이디입니다."})

    new_user = User(
        user_username=userId,
        user_pw=hash_password(userPw)
    )
    
    db.add(new_user)
    db.commit()

    return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

# =====================================================
# 로그인 페이지 (GET)
# =====================================================
@router.get("/auth/login")
def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})

# =====================================================
# 로그인 처리 (POST)
# =====================================================
@router.post("/auth/login")
def login(
    request: Request,
    userId: str = Form(...),
    userPw: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.user_username == userId).first()

    # 아이디가 없거나 비밀번호가 틀리면 에러 반환
    if not user or not verify_password(userPw, user.user_pw):
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "아이디 또는 비밀번호가 일치하지 않습니다."}
        )

    # 성공 시 메인 페이지로 이동
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    # 로그인 상태 유지를 위한 쿠키 발급
    response.set_cookie(key="login_user", value=user.user_username)
    return response

# =====================================================
# 로그아웃 처리 (GET)
# =====================================================
@router.get("/auth/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    # 쿠키 삭제를 통한 로그아웃 처리
    response.delete_cookie(key="login_user")
    return response
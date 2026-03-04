import re
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from starlette import status
from pydantic import BaseModel

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

# JSON 요청 본문을 받기 위한 Pydantic 스키마
class PasswordChangeRequest(BaseModel):
    new_password: str

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

    if not user or not verify_password(userPw, user.user_pw):
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "아이디 또는 비밀번호가 일치하지 않습니다."}
        )

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    # ✅ 쿠키 발급 시 path="/" 명시 (전체 사이트에서 동일한 쿠키 사용)
    response.set_cookie(key="login_user", value=user.user_username, path="/")
    return response

# =====================================================
# 로그아웃 처리 (GET)
# =====================================================
@router.get("/auth/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    # ✅ 쿠키 삭제 시 path="/" 명시
    response.delete_cookie(key="login_user", path="/")
    return response

# =====================================================
# 아이디 중복 확인 API (GET)
# =====================================================
@router.get("/auth/check-id")
def check_id(userId: str, db: Session = Depends(get_db)):
    if not re.match(ID_REGEX, userId):
        return {"exists": False, "invalid_format": True}

    existing_user = db.query(User).filter(User.user_username == userId).first()
    
    if existing_user:
        return {"exists": True, "invalid_format": False}
        
    return {"exists": False, "invalid_format": False}

# =====================================================
# 비밀번호 변경 API (POST)
# =====================================================
@router.post("/auth/change-password")
def change_password(
    request: Request,
    data: PasswordChangeRequest,
    db: Session = Depends(get_db)
):
    user_id = request.cookies.get("login_user")
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "로그인이 필요합니다."})
        
    if not re.match(PW_REGEX, data.new_password):
        return JSONResponse(status_code=400, content={"detail": "비밀번호 형식이 올바르지 않습니다."})
        
    user = db.query(User).filter(User.user_username == user_id).first()
    if not user:
        return JSONResponse(status_code=404, content={"detail": "사용자를 찾을 수 없습니다."})
        
    if verify_password(data.new_password, user.user_pw):
        return JSONResponse(status_code=400, content={"detail": "기존 비밀번호와 동일합니다. 다른 비밀번호를 사용해 주세요."})
        
    user.user_pw = hash_password(data.new_password)
    db.commit()
    
    response = JSONResponse(content={"message": "비밀번호가 성공적으로 변경되었습니다."})
    # ✅ 백엔드에서도 쿠키 삭제 시 path="/" 명시
    response.delete_cookie(key="login_user", path="/")
    return response
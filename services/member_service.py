import re
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from starlette import status

# 🚀 FastAPI() 대신 APIRouter()를 사용합니다.
router = APIRouter()

# -----------------------
# template 설정 (static 설정은 main.py로 이동)
# -----------------------
templates = Jinja2Templates(directory="templates")

# -----------------------
# 비밀번호 해싱 설정
# -----------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# -----------------------
# 정규식
# -----------------------
ID_REGEX = r"^[A-Za-z0-9]{6,20}$"
PW_REGEX = r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&]).{8,}$"

# -----------------------
# 가짜 DB
# -----------------------
fake_db = {}


def hash_password(password: str):
    return pwd_context.hash(password)


# =====================================================
# 회원가입 페이지 (GET)
# =====================================================
# 🚀 @app.get 대신 @router.get을 사용합니다.
@router.get("/auth/signup")
def signup_page(request: Request):
    return templates.TemplateResponse(
        "auth/signup.html",
        {"request": request}
    )


# =====================================================
# 회원가입 처리 (POST)
# =====================================================
# 🚀 @app.post 대신 @router.post를 사용합니다.
@router.post("/auth/signup")
def signup(
    request: Request,
    userId: str = Form(...),
    userPw: str = Form(...),
    userPwConfirm: str = Form(...)
):
    # 중복 검사
    if userId in fake_db:
        return templates.TemplateResponse(
            "auth/signup.html",
            {"request": request, "error": "이미 존재하는 아이디입니다."}
        )

    # 아이디 형식 검사
    if not re.match(ID_REGEX, userId):
        return templates.TemplateResponse(
            "auth/signup.html",
            {"request": request, "error": "아이디 형식이 올바르지 않습니다."}
        )

    # 비밀번호 형식 검사
    if not re.match(PW_REGEX, userPw):
        return templates.TemplateResponse(
            "auth/signup.html",
            {"request": request, "error": "비밀번호 형식이 올바르지 않습니다."}
        )

    # 비밀번호 일치 검사
    if userPw != userPwConfirm:
        return templates.TemplateResponse(
            "auth/signup.html",
            {"request": request, "error": "비밀번호가 일치하지 않습니다."}
        )

    # 저장
    fake_db[userId] = {
        "password": hash_password(userPw),
        "is_deleted": 0
    }

    # 성공 → 로그인 페이지로 이동 (POST -> GET 리다이렉트를 위해 303 강제 지정)
    return RedirectResponse(
        url="/auth/login",
        status_code=status.HTTP_303_SEE_OTHER
    )


# =====================================================
# 로그인 페이지 (GET)
# =====================================================
@router.get("/auth/login")
def login_page(request: Request):
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request}
    )
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
    # DB에서 유저 조회
    user = db.query(User).filter(User.user_username == userId).first()

    # 1. 아이디가 없거나 비밀번호가 틀린 경우
    if not user or not verify_password(userPw, user.user_pw):
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "아이디 또는 비밀번호가 일치하지 않습니다."}
        )

    # ✅ 2. 탈퇴한 회원(user_status == 0)인 경우 로그인 차단
    if user.user_status == 0:
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "탈퇴 처리된 계정입니다."}
        )

    # 성공 시 메인 페이지로 이동
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    # 쿠키 발급 시 path="/" 명시
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

@router.post("/auth/change-password")
def change_password(
    request: Request,
    data: PasswordChangeRequest,
    db: Session = Depends(get_db)
):
    user_id = request.cookies.get("login_user")
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "로그인이 필요합니다."})
        
    user = db.query(User).filter(User.user_username == user_id).first()
    if not user:
        return JSONResponse(status_code=404, content={"detail": "사용자를 찾을 수 없습니다."})
        
    # ✅ 3. 현재 비밀번호가 맞는지 검증
    if not verify_password(data.current_password, user.user_pw):
        return JSONResponse(status_code=400, content={"detail": "현재 비밀번호가 일치하지 않습니다."})
        
    # 4. 새 비밀번호 형식 검증
    if not re.match(PW_REGEX, data.new_password):
        return JSONResponse(status_code=400, content={"detail": "새 비밀번호 형식이 올바르지 않습니다."})
        
    # 5. 새 비밀번호가 현재 비밀번호와 같은지 검증
    if verify_password(data.new_password, user.user_pw):
        return JSONResponse(status_code=400, content={"detail": "기존 비밀번호와 동일합니다. 다른 비밀번호를 사용해 주세요."})
        
    # 6. 통과 시 새 비밀번호 해싱 후 저장
    user.user_pw = hash_password(data.new_password)
    db.commit()
    
    response = JSONResponse(content={"message": "비밀번호가 성공적으로 변경되었습니다. 다시 로그인해주세요."})
    response.delete_cookie(key="login_user", path="/")
    return response

# =====================================================
# 회원 탈퇴 API (POST)
# =====================================================
@router.post("/auth/withdraw")
def withdraw_user(
    request: Request,
    db: Session = Depends(get_db)
):
    # 1. 로그인 여부 확인 (쿠키에서 가져오기)
    user_id = request.cookies.get("login_user")
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "로그인이 필요합니다."})
        
    # 2. DB에서 유저 조회
    user = db.query(User).filter(User.user_username == user_id).first()
    if not user:
        return JSONResponse(status_code=404, content={"detail": "사용자를 찾을 수 없습니다."})
        
    # 3. 회원 상태 변경 (user_status = 0 으로 소프트 딜리트)
    user.user_status = 0
    db.commit()
    
    # 4. 성공 응답 및 쿠키 삭제 (강제 로그아웃 처리)
    response = JSONResponse(content={"message": "회원 탈퇴가 완료되었습니다. 그동안 이용해 주셔서 감사합니다."})
    response.delete_cookie(key="login_user", path="/")
    return response

# =====================================================
# 피드백 페이지 (GET) - ⭐️ 새롭게 추가된 부분
# =====================================================
@router.get("/resume/feedback")
def feedback_page(request: Request, db: Session = Depends(get_db)):
    # 1. 로그인 체크
    user_id = request.cookies.get("login_user")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
        
    # 2. 유저의 이력서 조회 (실제 DB 연동 시 아래 주석 해제 후 맞게 수정하세요)
    # resumes = db.query(Resume).filter(Resume.user_username == user_id).all()
    
    # 지금은 테스트를 위해 일부러 빈 리스트를 넘깁니다.
    # 이 빈 리스트가 HTML로 넘어가야 HTML 파일의 {% if not resumes %}가 드디어 작동합니다!
    resumes = [] 
    
    return templates.TemplateResponse("feedback.html", {"request": request, "resumes": resumes})
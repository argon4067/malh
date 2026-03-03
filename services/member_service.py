import re
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from passlib.context import CryptContext

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ID_REGEX = r"^[A-Za-z0-9]{6,20}$"
PW_REGEX = r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&]).{8,}$"


# -----------------------
# 🔹 가짜 DB (테스트용)
# 실제로는 MySQL/SQLite 사용
# -----------------------
fake_db = {}
# 구조:
# fake_db[userId] = {
#     "password": 해시값,
#     "is_deleted": 0 또는 1
# }


# -----------------------
# 모델
# -----------------------
class SignupRequest(BaseModel):
    userId: str
    userPw: str


class ChangePasswordRequest(BaseModel):
    userId: str
    currentPw: str
    newPw: str


class DeleteUserRequest(BaseModel):
    userId: str


# -----------------------
# 해싱 관련 함수
# -----------------------
def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


# -----------------------
# 회원가입 페이지
# -----------------------
@app.get("/signup")
def signup_page(request: Request):
    return templates.TemplateResponse(
        "auth/signup.html",
        {"request": request}
    )


# -----------------------
# 회원가입
# -----------------------
@app.post("/signup")
def signup(data: SignupRequest):

    if data.userId in fake_db:
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다.")

    if not re.match(ID_REGEX, data.userId):
        raise HTTPException(status_code=400, detail="아이디 형식이 올바르지 않습니다.")

    if not re.match(PW_REGEX, data.userPw):
        raise HTTPException(status_code=400, detail="비밀번호 형식이 올바르지 않습니다.")

    hashed_pw = hash_password(data.userPw)

    fake_db[data.userId] = {
        "password": hashed_pw,
        "is_deleted": 0
    }

    return {"message": "회원가입 성공"}


# -----------------------
# 🔐 비밀번호 변경
# -----------------------
@app.put("/change-password")
def change_password(data: ChangePasswordRequest):

    user = fake_db.get(data.userId)

    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    if user["is_deleted"] == 1:
        raise HTTPException(status_code=400, detail="탈퇴한 회원입니다.")

    # 현재 비밀번호 확인
    if not verify_password(data.currentPw, user["password"]):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 틀렸습니다.")

    # 새 비밀번호 정규식 검사
    if not re.match(PW_REGEX, data.newPw):
        raise HTTPException(status_code=400, detail="새 비밀번호 형식이 올바르지 않습니다.")

    # 새 비밀번호 해싱 후 저장
    user["password"] = hash_password(data.newPw)

    return {"message": "비밀번호 변경 완료"}


# -----------------------
# 🚪 회원탈퇴 (소프트 삭제)
# -----------------------
@app.delete("/delete-user")
def delete_user(data: DeleteUserRequest):

    user = fake_db.get(data.userId)

    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    if user["is_deleted"] == 1:
        raise HTTPException(status_code=400, detail="이미 탈퇴한 회원입니다.")

    user["is_deleted"] = 1

    return {"message": "회원 탈퇴 완료"}
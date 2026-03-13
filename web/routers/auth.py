from fastapi import APIRouter, Request
from web.common import templates

router = APIRouter()

# Auth
@router.get("/auth/login")
async def login(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})

@router.get("/auth/agree")
async def agree(request: Request):
    return templates.TemplateResponse("auth/agree.html", {"request": request})

@router.get("/auth/signup")
async def signup(request: Request):
    return templates.TemplateResponse("auth/signup.html", {"request": request})

# Account
@router.get("/account/password")
async def account_password(request: Request):
    return templates.TemplateResponse("account/password.html", {"request": request})

@router.get("/account/withdraw")
async def account_withdraw(request: Request):
    return templates.TemplateResponse("account/withdraw.html", {"request": request})

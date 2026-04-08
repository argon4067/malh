from fastapi import APIRouter, Request
from web.common import templates
from web.routers import auth, resume, interview, result, weakness

web_router = APIRouter()

# 메인 및 서비스 안내 페이지
@web_router.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@web_router.get("/service-intro")
async def service_intro(request: Request):
    return templates.TemplateResponse(request=request, name="service_intro.html")

@web_router.get("/how-to-use")
async def how_to_use(request: Request):
    return templates.TemplateResponse(request=request, name="how_to_use.html")

# 도메인별 분리된 라우터 포함
web_router.include_router(auth.router)
web_router.include_router(resume.router)
web_router.include_router(interview.router)
web_router.include_router(result.router)
web_router.include_router(weakness.router)

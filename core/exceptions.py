from typing import Any, Dict, Optional
from fastapi import status

class BaseAPIException(Exception):
    """모든 커스텀 예외의 기본 클래스"""
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "서버 내부 오류가 발생했습니다."
    code: str = "INTERNAL_SERVER_ERROR"

    def __init__(
        self, 
        detail: Optional[str] = None, 
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ):
        if detail:
            self.detail = detail
        if status_code:
            self.status_code = status_code
        if code:
            self.code = code
        self.data = data or {}
        super().__init__(self.detail)

class BadRequestException(BaseAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "잘못된 요청입니다."
    code = "BAD_REQUEST"

class UnauthorizedException(BaseAPIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "인증되지 않은 사용자입니다."
    code = "UNAUTHORIZED"

class ForbiddenException(BaseAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "권한이 없습니다."
    code = "FORBIDDEN"

class NotFoundException(BaseAPIException):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "요청한 자원을 찾을 수 없습니다."
    code = "NOT_FOUND"

class ConflictException(BaseAPIException):
    status_code = status.HTTP_409_CONFLICT
    detail = "리소스 충돌이 발생했습니다."
    code = "CONFLICT"

class ValidationException(BaseAPIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    detail = "입력값 검증에 실패했습니다."
    code = "VALIDATION_ERROR"

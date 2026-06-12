"""Tavily 호환 에러 응답 형식: {"detail": {"error": "<message>"}}."""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """서비스 전역에서 사용하는 API 예외. Spring의 @ResponseStatus 예외에 대응."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class UnauthorizedError(ApiError):
    def __init__(self, message: str = "Unauthorized: missing or invalid API key.") -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, message)


class UpstreamError(ApiError):
    """외부 검색엔진/크롤러 호출 실패 → 502 Bad Gateway."""

    def __init__(self, message: str) -> None:
        super().__init__(status.HTTP_502_BAD_GATEWAY, message)


def register_exception_handlers(app: FastAPI) -> None:
    """Spring의 @ControllerAdvice + @ExceptionHandler에 대응."""

    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": {"error": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI 기본은 422이지만 Tavily는 잘못된 요청에 400을 반환하므로 맞춰준다.
        errors = exc.errors()
        if errors:
            first = errors[0]
            location = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
            message = f"{location}: {first.get('msg', 'invalid request')}"
        else:
            message = "Invalid request body."
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": {"error": message}},
        )

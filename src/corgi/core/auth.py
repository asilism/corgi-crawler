"""API 키 인증.

Tavily 호환을 위해 두 방식을 모두 지원한다:
- Authorization: Bearer <key> 헤더 (현행 방식)
- 요청 바디의 api_key 필드 (구버전 클라이언트 호환)
"""

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from corgi.core.config import Settings
from corgi.core.exceptions import UnauthorizedError

# auto_error=False: 헤더가 없어도 403을 던지지 않고 None을 넘긴다.
# (바디 api_key로 인증할 수 있으므로 헤더 부재가 곧 실패는 아님)
bearer_scheme = HTTPBearer(auto_error=False)


def require_api_key(
    settings: Settings,
    credentials: HTTPAuthorizationCredentials | None,
    body_api_key: str | None,
) -> None:
    """허용된 키가 아니면 UnauthorizedError(401)를 던진다."""
    allowed = settings.allowed_api_keys
    if not allowed:  # 키 미설정 = 로컬 개발 모드, 인증 생략
        return

    bearer_key = credentials.credentials if credentials else None
    for candidate in (bearer_key, body_api_key):
        if candidate and candidate in allowed:
            return
    raise UnauthorizedError()

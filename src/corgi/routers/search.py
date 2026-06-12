"""POST /search 라우터. Spring의 @RestController에 대응 — 검증/위임만 한다."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials

from corgi.core.auth import bearer_scheme, require_api_key
from corgi.core.dependencies import SettingsDep, get_search_service
from corgi.schemas.search import SearchRequest, SearchResponse
from corgi.services.search_service import SearchService

router = APIRouter(tags=["search"])


@router.post("/search")
async def search(
    request: SearchRequest,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: SettingsDep,
    service: Annotated[SearchService, Depends(get_search_service)],
) -> SearchResponse:
    require_api_key(settings, credentials, request.api_key)
    return await service.search(request)

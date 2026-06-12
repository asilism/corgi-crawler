"""POST /extract 라우터. Spring의 @RestController에 대응 — 검증/위임만 한다."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials

from corgi.core.auth import bearer_scheme, require_api_key
from corgi.core.dependencies import SettingsDep, get_extract_service
from corgi.schemas.extract import ExtractRequest, ExtractResponse
from corgi.services.extract_service import ExtractService

router = APIRouter(tags=["extract"])


@router.post("/extract")
async def extract(
    request: ExtractRequest,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: SettingsDep,
    service: Annotated[ExtractService, Depends(get_extract_service)],
) -> ExtractResponse:
    require_api_key(settings, credentials, request.api_key)
    return await service.extract(request)

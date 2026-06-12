"""POST /extract 요청/응답 DTO — Tavily Extract API 스펙과 필드명/타입 동일."""

from typing import Literal

from pydantic import BaseModel, Field


class ExtractRequest(BaseModel):
    # Tavily 스펙: 단일 URL 문자열 또는 URL 배열 둘 다 허용
    urls: str | list[str]
    api_key: str | None = None
    include_images: bool = False
    include_favicon: bool = False
    extract_depth: Literal["basic", "advanced"] = "basic"
    format: Literal["markdown", "text"] = "markdown"
    timeout: float | None = Field(default=None, ge=1.0, le=60.0)


class ExtractResult(BaseModel):
    url: str
    raw_content: str
    images: list[str] = Field(default_factory=list)
    favicon: str | None = None


class FailedResult(BaseModel):
    url: str
    error: str


class ExtractResponse(BaseModel):
    results: list[ExtractResult] = Field(default_factory=list)
    failed_results: list[FailedResult] = Field(default_factory=list)
    response_time: float
    request_id: str

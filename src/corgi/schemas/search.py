"""POST /search 요청/응답 DTO — Tavily Search API 스펙과 필드명/타입 동일."""

from typing import Literal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    # 구버전 Tavily 클라이언트는 바디로 키를 보낸다. 헤더 인증과 함께 지원.
    api_key: str | None = None
    auto_parameters: bool = False
    topic: Literal["general", "news", "finance"] = "general"
    search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = "basic"
    chunks_per_source: int = Field(default=3, ge=1, le=3)
    max_results: int = Field(default=5, ge=0, le=20)
    time_range: Literal["day", "week", "month", "year", "d", "w", "m", "y"] | None = None
    days: int = Field(default=7, ge=1)
    start_date: str | None = None
    end_date: str | None = None
    # Tavily 스펙: bool 또는 "basic"/"advanced" 문자열 둘 다 허용
    include_answer: bool | Literal["basic", "advanced"] = False
    # Tavily 스펙: bool 또는 "markdown"/"text" 문자열 둘 다 허용
    include_raw_content: bool | Literal["markdown", "text"] = False
    include_images: bool = False
    include_image_descriptions: bool = False
    include_favicon: bool = False
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    country: str | None = None


class ImageResult(BaseModel):
    url: str
    description: str | None = None


class SearchResult(BaseModel):
    title: str
    url: str
    content: str
    score: float
    raw_content: str | None = None
    favicon: str | None = None


class SearchResponse(BaseModel):
    query: str
    follow_up_questions: list[str] | None = None
    answer: str | None = None
    # include_image_descriptions=False면 URL 문자열, True면 객체 목록 (Tavily 동작)
    images: list[str | ImageResult] = Field(default_factory=list)
    results: list[SearchResult] = Field(default_factory=list)
    response_time: float
    request_id: str

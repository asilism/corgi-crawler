"""FastAPI Depends 조립부. Spring의 @Configuration + 생성자 주입에 대응.

각 함수가 빈 팩토리 역할을 하고, FastAPI가 요청마다 의존성 그래프를
해석해서 주입한다. 테스트에서는 app.dependency_overrides로 교체한다.
"""

from typing import Annotated

import httpx
from fastapi import Depends, Request

from corgi.core.config import Settings, get_settings
from corgi.providers.base import Crawler, SearchProvider
from corgi.providers.duckduckgo import DuckDuckGoSearchProvider
from corgi.providers.httpx_crawler import HttpxCrawler
from corgi.services.extract_service import ExtractService
from corgi.services.search_service import SearchService

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_http_client(request: Request) -> httpx.AsyncClient:
    # lifespan(main.py)에서 만들어 app.state에 둔 공유 클라이언트.
    # 요청마다 커넥션 풀을 새로 만들지 않기 위함.
    client = request.app.state.http_client
    assert isinstance(client, httpx.AsyncClient)
    return client


HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]


def get_search_provider(client: HttpClientDep) -> SearchProvider:
    return DuckDuckGoSearchProvider(client)


def get_crawler(client: HttpClientDep, settings: SettingsDep) -> Crawler:
    return HttpxCrawler(client, default_timeout=settings.http_timeout)


def get_search_service(
    provider: Annotated[SearchProvider, Depends(get_search_provider)],
    crawler: Annotated[Crawler, Depends(get_crawler)],
    settings: SettingsDep,
) -> SearchService:
    return SearchService(provider, crawler, settings)


def get_extract_service(
    crawler: Annotated[Crawler, Depends(get_crawler)],
    settings: SettingsDep,
) -> ExtractService:
    return ExtractService(crawler, settings)

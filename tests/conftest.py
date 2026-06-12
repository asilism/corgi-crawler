"""테스트 픽스처.

Fake 구현체를 dependency_overrides로 주입한다
(Spring에서 @MockBean으로 빈을 갈아끼우는 것에 대응).
"""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from corgi.core.config import Settings, get_settings
from corgi.core.dependencies import get_crawler, get_search_provider
from corgi.main import create_app
from corgi.providers.base import CrawledPage, WebSearchHit

TEST_API_KEY = "tvly-test-key"

HITS = [
    WebSearchHit(
        title="Corgi facts",
        url="https://dogs.example.com/corgi",
        snippet="Corgis are small herding dogs from Wales.",
        score=1.0,
    ),
    WebSearchHit(
        title="Corgi history",
        url="https://blog.wiki.example.org/corgi-history",
        snippet="The Pembroke Welsh Corgi dates back centuries.",
        score=0.95,
    ),
    WebSearchHit(
        title="Corgi cafe",
        url="https://cafe.example.net/menu",
        snippet="A cafe themed around corgis.",
        score=0.9,
    ),
]

PAGES = {
    "https://dogs.example.com/corgi": CrawledPage(
        url="https://dogs.example.com/corgi",
        title="Corgi facts",
        text="Corgis are small herding dogs.\nThey have short legs.",
        markdown="# Corgi facts\n\nCorgis are small herding dogs.",
        image_urls=("https://dogs.example.com/corgi.jpg",),
        favicon="https://dogs.example.com/favicon.ico",
    ),
    "https://blog.wiki.example.org/corgi-history": CrawledPage(
        url="https://blog.wiki.example.org/corgi-history",
        title="Corgi history",
        text="The Pembroke Welsh Corgi dates back centuries.",
        markdown="# Corgi history\n\nThe Pembroke Welsh Corgi dates back centuries.",
    ),
}


class FakeSearchProvider:
    async def search(self, query: str, *, max_results: int) -> list[WebSearchHit]:
        return HITS[:max_results]


class FakeCrawler:
    async def fetch(self, url: str, *, timeout: float | None = None) -> CrawledPage:
        if url not in PAGES:
            raise RuntimeError(f"connection refused: {url}")
        return PAGES[url]


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: Settings(api_keys=TEST_API_KEY)
    application.dependency_overrides[get_search_provider] = FakeSearchProvider
    application.dependency_overrides[get_crawler] = FakeCrawler
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    # ASGITransport: 실제 소켓 없이 앱을 in-process로 호출 (Spring의 MockMvc에 대응)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_API_KEY}"}

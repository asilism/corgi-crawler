from fastapi import FastAPI
from httpx import AsyncClient

from corgi.core.dependencies import get_search_provider
from corgi.core.exceptions import UpstreamError
from corgi.providers.base import WebSearchHit


async def test_search_response_schema(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post("/search", json={"query": "corgi"}, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    # Tavily 응답 최상위 필드
    assert body["query"] == "corgi"
    assert body["answer"] is None  # include_answer 기본값 False
    assert body["follow_up_questions"] is None
    assert isinstance(body["images"], list)
    assert isinstance(body["response_time"], float)
    assert isinstance(body["request_id"], str)

    # 결과 항목 필드 (title, url, content, score, raw_content)
    first = body["results"][0]
    assert first["title"] == "Corgi facts"
    assert first["url"] == "https://dogs.example.com/corgi"
    assert first["content"].startswith("Corgis are small")
    assert isinstance(first["score"], float)
    assert first["raw_content"] is None  # include_raw_content 기본값 False


async def test_max_results(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post(
        "/search", json={"query": "corgi", "max_results": 2}, headers=auth_headers
    )
    assert len(response.json()["results"]) == 2


async def test_include_answer(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post(
        "/search", json={"query": "corgi", "include_answer": True}, headers=auth_headers
    )
    answer = response.json()["answer"]
    assert answer is not None
    assert "herding dogs" in answer


async def test_include_raw_content(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post(
        "/search",
        json={"query": "corgi", "include_raw_content": True, "max_results": 3},
        headers=auth_headers,
    )
    results = {r["url"]: r for r in response.json()["results"]}
    assert results["https://dogs.example.com/corgi"]["raw_content"].startswith("# Corgi facts")
    # 크롤링이 실패한 URL은 raw_content가 null이어야 한다 (검색 자체는 성공)
    assert results["https://cafe.example.net/menu"]["raw_content"] is None


async def test_include_raw_content_text_mode(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/search",
        json={"query": "corgi", "include_raw_content": "text", "max_results": 1},
        headers=auth_headers,
    )
    raw = response.json()["results"][0]["raw_content"]
    assert raw.startswith("Corgis are small herding dogs.")


async def test_include_domains(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post(
        "/search",
        json={"query": "corgi", "include_domains": ["example.com"]},
        headers=auth_headers,
    )
    urls = [r["url"] for r in response.json()["results"]]
    # 서브도메인(dogs.example.com)도 example.com 필터에 매칭되어야 한다
    assert urls == ["https://dogs.example.com/corgi"]


async def test_exclude_domains(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post(
        "/search",
        json={"query": "corgi", "exclude_domains": ["example.com", "example.org"]},
        headers=auth_headers,
    )
    urls = [r["url"] for r in response.json()["results"]]
    assert urls == ["https://cafe.example.net/menu"]


async def test_missing_query_returns_400(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    # Tavily는 검증 실패에 422가 아닌 400을 반환한다
    response = await client.post("/search", json={}, headers=auth_headers)
    assert response.status_code == 400
    assert "error" in response.json()["detail"]


async def test_provider_failure_returns_502(
    app: FastAPI, client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    class BrokenProvider:
        async def search(self, query: str, *, max_results: int) -> list[WebSearchHit]:
            raise UpstreamError("Search provider request failed: connection refused")

    app.dependency_overrides[get_search_provider] = BrokenProvider

    response = await client.post("/search", json={"query": "corgi"}, headers=auth_headers)
    assert response.status_code == 502
    assert "Search provider request failed" in response.json()["detail"]["error"]

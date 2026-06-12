from httpx import AsyncClient

from tests.conftest import TEST_API_KEY


async def test_missing_api_key_returns_401(client: AsyncClient) -> None:
    response = await client.post("/search", json={"query": "corgi"})
    assert response.status_code == 401
    assert response.json() == {"detail": {"error": "Unauthorized: missing or invalid API key."}}


async def test_invalid_bearer_key_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/search",
        json={"query": "corgi"},
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert response.status_code == 401


async def test_bearer_header_auth(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post("/search", json={"query": "corgi"}, headers=auth_headers)
    assert response.status_code == 200


async def test_body_api_key_auth(client: AsyncClient) -> None:
    # 구버전 Tavily 클라이언트 방식: 바디의 api_key 필드
    response = await client.post("/search", json={"query": "corgi", "api_key": TEST_API_KEY})
    assert response.status_code == 200

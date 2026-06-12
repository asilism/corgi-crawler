from httpx import AsyncClient


async def test_extract_single_url_as_string(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    # Tavily 스펙: urls는 배열뿐 아니라 단일 문자열도 허용
    response = await client.post(
        "/extract",
        json={"urls": "https://dogs.example.com/corgi"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["url"] == "https://dogs.example.com/corgi"
    assert body["results"][0]["raw_content"].startswith("# Corgi facts")
    assert body["failed_results"] == []
    assert isinstance(body["response_time"], float)


async def test_extract_mixed_success_and_failure(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/extract",
        json={
            "urls": [
                "https://dogs.example.com/corgi",
                "https://unreachable.example.com/404",
            ]
        },
        headers=auth_headers,
    )
    body = response.json()
    assert [r["url"] for r in body["results"]] == ["https://dogs.example.com/corgi"]
    assert [f["url"] for f in body["failed_results"]] == ["https://unreachable.example.com/404"]
    assert "connection refused" in body["failed_results"][0]["error"]


async def test_extract_text_format(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post(
        "/extract",
        json={"urls": ["https://dogs.example.com/corgi"], "format": "text"},
        headers=auth_headers,
    )
    raw = response.json()["results"][0]["raw_content"]
    assert raw.startswith("Corgis are small herding dogs.")


async def test_extract_include_images_and_favicon(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/extract",
        json={
            "urls": ["https://dogs.example.com/corgi"],
            "include_images": True,
            "include_favicon": True,
        },
        headers=auth_headers,
    )
    result = response.json()["results"][0]
    assert result["images"] == ["https://dogs.example.com/corgi.jpg"]
    assert result["favicon"] == "https://dogs.example.com/favicon.ico"


async def test_extract_images_omitted_by_default(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/extract",
        json={"urls": ["https://dogs.example.com/corgi"]},
        headers=auth_headers,
    )
    result = response.json()["results"][0]
    assert result["images"] == []
    assert result["favicon"] is None

"""end-to-end: search_backend="index"로 자체 인덱스를 통해 /search 동작 확인."""

from pathlib import Path

from httpx import ASGITransport, AsyncClient

from corgi.core.config import Settings, get_settings
from corgi.core.dependencies import get_crawler, get_search_provider
from corgi.main import create_app
from corgi.providers.sqlite_index import IndexedDocument, SqliteIndex
from tests.conftest import TEST_API_KEY, FakeCrawler


async def test_search_served_from_local_index(tmp_path: Path) -> None:
    db_path = str(tmp_path / "index.db")
    index = SqliteIndex(db_path)
    index.initialize()
    index.upsert_many(
        [
            IndexedDocument(
                url="https://docs.example.com/corgi",
                title="Corgi guide",
                content="Everything about the corgi breed and its history.",
            ),
            IndexedDocument(
                url="https://docs.example.com/poodle",
                title="Poodle guide",
                content="A poodle is a different dog breed entirely.",
            ),
        ]
    )

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        api_keys=TEST_API_KEY, search_backend="index", index_path=db_path
    )
    app.dependency_overrides[get_search_provider] = lambda: SqliteIndex(db_path)
    # raw_content를 안 쓰므로 크롤러는 호출되지 않지만, DI 그래프 해석을 위해 스텁 주입
    app.dependency_overrides[get_crawler] = FakeCrawler

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/search",
            json={"query": "corgi"},
            headers={"Authorization": f"Bearer {TEST_API_KEY}"},
        )

    assert response.status_code == 200
    results = response.json()["results"]
    # 자체 인덱스에서 corgi 문서만 매칭되어 돌아와야 한다
    assert [r["url"] for r in results] == ["https://docs.example.com/corgi"]
    assert results[0]["score"] == 1.0

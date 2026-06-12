"""SqliteIndex(자체 색인) 단위 테스트."""

from pathlib import Path

import pytest

from corgi.core.exceptions import UpstreamError
from corgi.providers.sqlite_index import IndexedDocument, SqliteIndex, _to_match_query

DOCS = [
    IndexedDocument(
        url="https://a.example.com/corgi",
        title="All about Corgis",
        content="The corgi is a small herding dog. Corgi corgi corgi everywhere.",
    ),
    IndexedDocument(
        url="https://a.example.com/cat",
        title="Cats",
        content="Cats are felines. Nothing about dogs here at all.",
    ),
    IndexedDocument(
        url="https://a.example.com/dog",
        title="Dogs",
        content="A corgi is one breed of dog among many breeds.",
    ),
]


def _fresh_index(tmp_path: Path) -> SqliteIndex:
    index = SqliteIndex(str(tmp_path / "index.db"))
    index.initialize()
    return index


async def test_roundtrip_and_bm25_ranking(tmp_path: Path) -> None:
    index = _fresh_index(tmp_path)
    index.upsert_many(DOCS)
    assert index.count() == 3

    hits = await index.search("corgi", max_results=10)
    urls = [h.url for h in hits]

    # "corgi"를 가장 많이 언급한 문서가 1위, 매칭 없는 cat은 제외
    assert hits[0].url == "https://a.example.com/corgi"
    assert "https://a.example.com/dog" in urls
    assert "https://a.example.com/cat" not in urls
    # 점수는 0~1로 정규화되고 1위가 1.0
    assert hits[0].score == 1.0
    assert all(0.0 < h.score <= 1.0 for h in hits)
    # 스니펫이 채워져 있어야 한다 (content 필드로 매핑됨)
    assert hits[0].snippet


async def test_upsert_is_idempotent(tmp_path: Path) -> None:
    index = _fresh_index(tmp_path)
    doc = IndexedDocument(url="https://x.example/y", title="t", content="corgi content")
    index.upsert_many([doc])
    index.upsert_many([doc])  # 같은 URL 재색인
    assert index.count() == 1


async def test_upsert_overwrites_existing_url(tmp_path: Path) -> None:
    index = _fresh_index(tmp_path)
    index.upsert_many([IndexedDocument(url="https://x.example/y", title="old", content="apple")])
    index.upsert_many([IndexedDocument(url="https://x.example/y", title="new", content="corgi")])
    assert index.count() == 1
    assert await index.search("apple", max_results=5) == []
    hits = await index.search("corgi", max_results=5)
    assert hits[0].title == "new"


async def test_max_results_limit(tmp_path: Path) -> None:
    index = _fresh_index(tmp_path)
    index.upsert_many(DOCS)
    assert len(await index.search("corgi", max_results=1)) == 1
    assert await index.search("corgi", max_results=0) == []


async def test_empty_query_returns_empty(tmp_path: Path) -> None:
    index = _fresh_index(tmp_path)
    index.upsert_many(DOCS)
    assert await index.search("   !!!  ", max_results=5) == []


async def test_search_on_missing_index_raises_upstream_error(tmp_path: Path) -> None:
    index = SqliteIndex(str(tmp_path / "does-not-exist.db"))
    with pytest.raises(UpstreamError):
        await index.search("corgi", max_results=5)


def test_to_match_query_escapes_and_ors() -> None:
    assert _to_match_query("welsh corgi") == '"welsh" OR "corgi"'
    assert _to_match_query("  ??? ") is None
    # 큰따옴표로 감싸므로 FTS5 특수문자가 주입되지 않는다
    assert _to_match_query('a "OR" b') == '"a" OR "OR" OR "b"'

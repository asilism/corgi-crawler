"""`corgi-crawl` 명령: 시드 도메인을 크롤링해 SQLite 인덱스에 색인한다.

실행: uv run corgi-crawl
설정은 환경변수(CORGI_CRAWL_SEEDS 등) 또는 .env에서 읽는다.
"""

import asyncio
import sys
from urllib.parse import urlparse

import httpx

from corgi.core.config import Settings, get_settings
from corgi.indexing.crawler import SiteCrawler
from corgi.providers.base import CrawledPage
from corgi.providers.httpx_crawler import HttpxCrawler
from corgi.providers.sqlite_index import IndexedDocument, SqliteIndex

_WRITE_BATCH = 20


def _derive_allowed_domains(seeds: list[str]) -> tuple[str, ...]:
    """시드 URL들의 호스트를 허용 도메인으로 삼는다 (사이트 밖으로 안 나감)."""
    hosts = {host.lower().removeprefix("www.") for seed in seeds if (host := urlparse(seed).netloc)}
    return tuple(sorted(hosts))


def _to_document(page: CrawledPage) -> IndexedDocument:
    # 색인 대상은 보일러플레이트를 제거한 본문 텍스트
    return IndexedDocument(url=page.url, title=page.title, content=page.text)


async def _run(settings: Settings, seeds: list[str]) -> int:
    index = SqliteIndex(settings.index_path)
    index.initialize()

    allowed = _derive_allowed_domains(seeds)
    print(f"시드 {len(seeds)}개, 허용 도메인: {', '.join(allowed)}")

    total = 0
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.http_timeout,
        follow_redirects=True,
    ) as client:
        site = SiteCrawler(
            HttpxCrawler(client, default_timeout=settings.http_timeout),
            client,
            allowed_domains=allowed,
            max_depth=settings.crawl_max_depth,
            max_pages=settings.crawl_max_pages,
            delay=settings.crawl_delay,
            user_agent=settings.user_agent,
            respect_robots=settings.crawl_respect_robots,
        )
        batch: list[IndexedDocument] = []
        async for page in site.crawl(seeds):
            batch.append(_to_document(page))
            if len(batch) >= _WRITE_BATCH:
                index.upsert_many(batch)
                total += len(batch)
                batch.clear()
                print(f"  ... {total}개 색인 완료")
        if batch:
            index.upsert_many(batch)
            total += len(batch)

    print(
        f"완료: {total}개 페이지를 '{settings.index_path}'에 색인했습니다 (총 {index.count()}개)."
    )
    return total


def main() -> None:
    settings = get_settings()
    seeds = settings.crawl_seed_list
    if not seeds:
        print(
            "크롤 대상이 없습니다. CORGI_CRAWL_SEEDS에 쉼표로 구분된 시드 URL을 설정하세요.\n"
            "예: CORGI_CRAWL_SEEDS=https://example.com,https://docs.example.com",
            file=sys.stderr,
        )
        raise SystemExit(1)
    asyncio.run(_run(settings, seeds))


if __name__ == "__main__":
    main()

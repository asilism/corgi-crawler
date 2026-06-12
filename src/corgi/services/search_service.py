"""검색 비즈니스 로직. Spring의 @Service에 대응."""

import asyncio
import time
from urllib.parse import urlparse
from uuid import uuid4

from corgi.core.config import Settings
from corgi.providers.base import Crawler, SearchProvider, WebSearchHit
from corgi.schemas.search import SearchRequest, SearchResponse, SearchResult

# 도메인 필터가 걸리면 잘려나갈 것을 감안해 provider에 넉넉히 요청한다
_OVERFETCH_FOR_FILTERING = 20


class SearchService:
    def __init__(self, provider: SearchProvider, crawler: Crawler, settings: Settings) -> None:
        self._provider = provider
        self._crawler = crawler
        self._settings = settings

    async def search(self, request: SearchRequest) -> SearchResponse:
        started = time.perf_counter()

        has_domain_filter = bool(request.include_domains or request.exclude_domains)
        fetch_count = (
            max(_OVERFETCH_FOR_FILTERING, request.max_results)
            if has_domain_filter
            else request.max_results
        )
        hits = await self._provider.search(request.query, max_results=fetch_count)
        hits = _filter_domains(hits, request.include_domains, request.exclude_domains)
        hits = hits[: request.max_results]

        raw_contents: dict[str, str | None] = {}
        if request.include_raw_content and hits:
            raw_contents = await self._fetch_raw_contents(hits, request.include_raw_content)

        results = [
            SearchResult(
                title=hit.title,
                url=hit.url,
                content=hit.snippet,
                score=hit.score,
                raw_content=raw_contents.get(hit.url),
            )
            for hit in hits
        ]
        answer = _compose_answer(results) if request.include_answer else None

        return SearchResponse(
            query=request.query,
            answer=answer,
            results=results,
            response_time=round(time.perf_counter() - started, 2),
            request_id=str(uuid4()),
        )

    async def _fetch_raw_contents(
        self, hits: list[WebSearchHit], mode: bool | str
    ) -> dict[str, str | None]:
        """결과 페이지 본문을 동시에(bounded) 수집한다. 실패한 URL은 None."""
        semaphore = asyncio.Semaphore(self._settings.max_concurrent_fetches)

        async def fetch_one(url: str) -> tuple[str, str | None]:
            async with semaphore:  # 동시 요청 수 제한 (커넥션 폭주 방지)
                try:
                    page = await self._crawler.fetch(url)
                except Exception:
                    # 일부 페이지 실패가 검색 전체를 망치면 안 되므로 삼킨다
                    return url, None
            return url, page.text if mode == "text" else page.markdown

        pairs = await asyncio.gather(*(fetch_one(hit.url) for hit in hits))
        return dict(pairs)


def _filter_domains(
    hits: list[WebSearchHit],
    include_domains: list[str],
    exclude_domains: list[str],
) -> list[WebSearchHit]:
    def domain_of(url: str) -> str:
        return urlparse(url).netloc.lower().removeprefix("www.")

    def matches(domain: str, patterns: list[str]) -> bool:
        # "example.com"은 서브도메인(blog.example.com)까지 포함해서 매칭
        return any(
            domain == p.lower().removeprefix("www.")
            or domain.endswith("." + p.lower().removeprefix("www."))
            for p in patterns
        )

    filtered = hits
    if include_domains:
        filtered = [h for h in filtered if matches(domain_of(h.url), include_domains)]
    if exclude_domains:
        filtered = [h for h in filtered if not matches(domain_of(h.url), exclude_domains)]
    return filtered


def _compose_answer(results: list[SearchResult], *, max_sources: int = 3) -> str:
    """상위 결과 스니펫을 이어 붙인 추출형 요약.

    Tavily는 LLM으로 답을 생성하지만, Corgi v1은 외부 LLM 의존 없이
    추출 방식으로 대체한다. LLM 연동 시 이 함수만 교체하면 된다.
    """
    snippets = [r.content.strip() for r in results[:max_sources] if r.content.strip()]
    return " ".join(snippets)

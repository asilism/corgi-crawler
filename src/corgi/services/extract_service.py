"""URL 본문 추출 비즈니스 로직. Spring의 @Service에 대응."""

import asyncio
import time
from uuid import uuid4

from corgi.core.config import Settings
from corgi.providers.base import CrawledPage, Crawler
from corgi.schemas.extract import (
    ExtractRequest,
    ExtractResponse,
    ExtractResult,
    FailedResult,
)


class ExtractService:
    def __init__(self, crawler: Crawler, settings: Settings) -> None:
        self._crawler = crawler
        self._settings = settings

    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        started = time.perf_counter()
        # Tavily 스펙상 urls는 문자열 하나일 수도, 배열일 수도 있다
        urls = [request.urls] if isinstance(request.urls, str) else request.urls

        semaphore = asyncio.Semaphore(self._settings.max_concurrent_fetches)

        async def fetch_one(url: str) -> CrawledPage | Exception:
            # 예외를 값으로 돌려받아 성공/실패를 한 번에 분류한다
            # (gather(return_exceptions=True)와 같은 효과지만 타입이 더 명확)
            async with semaphore:
                try:
                    return await self._crawler.fetch(url, timeout=request.timeout)
                except Exception as exc:
                    return exc

        outcomes = await asyncio.gather(*(fetch_one(url) for url in urls))

        results: list[ExtractResult] = []
        failed_results: list[FailedResult] = []
        for url, outcome in zip(urls, outcomes, strict=True):
            if isinstance(outcome, Exception):
                failed_results.append(FailedResult(url=url, error=str(outcome) or repr(outcome)))
            else:
                results.append(
                    ExtractResult(
                        url=url,
                        raw_content=(
                            outcome.text if request.format == "text" else outcome.markdown
                        ),
                        images=list(outcome.image_urls) if request.include_images else [],
                        favicon=outcome.favicon if request.include_favicon else None,
                    )
                )

        return ExtractResponse(
            results=results,
            failed_results=failed_results,
            response_time=round(time.perf_counter() - started, 2),
            request_id=str(uuid4()),
        )

"""시드 도메인을 BFS로 순회하는 사이트 크롤러.

Spring으로 치면 @Scheduled 배치 잡에 해당하는 오프라인 작업이다.
실제 페이지 fetch/추출은 Crawler(httpx) 어댑터에 위임하고, 여기서는
'어디까지 따라갈지'(도메인 경계, 깊이, 페이지 수, robots.txt)만 관리한다.
"""

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from corgi.providers.base import CrawledPage, Crawler


class SiteCrawler:
    def __init__(
        self,
        crawler: Crawler,
        client: httpx.AsyncClient,
        *,
        allowed_domains: tuple[str, ...],
        max_depth: int,
        max_pages: int,
        delay: float,
        user_agent: str,
        respect_robots: bool = True,
    ) -> None:
        self._crawler = crawler
        self._client = client
        # www. 접두사는 정규화해서 비교 (blog.example.com 같은 서브도메인 포함)
        self._allowed = tuple(d.lower().removeprefix("www.") for d in allowed_domains)
        self._max_depth = max_depth
        self._max_pages = max_pages
        self._delay = delay
        self._user_agent = user_agent
        self._respect_robots = respect_robots
        self._robots: dict[str, RobotFileParser] = {}

    async def crawl(self, seeds: list[str]) -> AsyncIterator[CrawledPage]:
        """방문한 페이지를 하나씩 yield하는 비동기 제너레이터.

        호출 측이 스트리밍으로 받아 색인하므로, 긴 크롤 중에도 메모리에
        전체 페이지를 쌓지 않는다.
        """
        queue: deque[tuple[str, int]] = deque((url, 0) for url in seeds)
        seen: set[str] = set(seeds)
        fetched = 0

        while queue and fetched < self._max_pages:
            url, depth = queue.popleft()
            if not self._host_allowed(url):
                continue
            if self._respect_robots and not await self._robots_ok(url):
                continue
            try:
                page = await self._crawler.fetch(url)
            except Exception:
                # 한 페이지 실패가 전체 크롤을 멈추면 안 된다
                continue

            fetched += 1
            yield page

            if depth < self._max_depth:
                for link in page.links:
                    if link not in seen and self._host_allowed(link):
                        seen.add(link)
                        queue.append((link, depth + 1))

            if self._delay > 0:
                await asyncio.sleep(self._delay)  # 서버 부하를 위한 예의상 지연

    def _host_allowed(self, url: str) -> bool:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        return any(host == d or host.endswith("." + d) for d in self._allowed)

    async def _robots_ok(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.netloc
        parser = self._robots.get(host)
        if parser is None:
            parser = RobotFileParser()
            try:
                response = await self._client.get(
                    f"{parsed.scheme}://{host}/robots.txt", timeout=5.0
                )
                # 200이면 규칙 적용, 그 외(404 등)는 빈 규칙 = 전체 허용
                parser.parse(response.text.splitlines() if response.status_code == 200 else [])
            except httpx.HTTPError:
                parser.parse([])  # robots를 못 받으면 보수적이지 않게 허용
            self._robots[host] = parser
        return parser.can_fetch(self._user_agent, url)

"""DuckDuckGo HTML 검색 어댑터.

API 키 없이 쓸 수 있는 html.duckduckgo.com 엔드포인트를 파싱한다.
다른 검색엔진(Google CSE, Bing, SearxNG 등)으로 바꾸려면
SearchProvider 프로토콜을 만족하는 클래스를 추가하면 된다.
"""

from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from corgi.core.exceptions import UpstreamError
from corgi.providers.base import WebSearchHit

_ENDPOINT = "https://html.duckduckgo.com/html/"
# 순위가 하나 내려갈 때마다 점수를 이만큼 깎는다 (단순 순위 기반 스코어링)
_RANK_DECAY = 0.05


class DuckDuckGoSearchProvider:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def search(self, query: str, *, max_results: int) -> list[WebSearchHit]:
        if max_results <= 0:
            return []
        try:
            response = await self._client.post(_ENDPOINT, data={"q": query, "kl": "us-en"})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # 업스트림 장애를 raw 500 대신 Tavily 형식의 502로 변환한다
            raise UpstreamError(f"Search provider request failed: {exc}") from exc
        return self._parse(response.text, max_results)

    def _parse(self, html: str, max_results: int) -> list[WebSearchHit]:
        soup = BeautifulSoup(html, "html.parser")
        hits: list[WebSearchHit] = []
        for rank, result in enumerate(soup.select("div.result")):
            anchor = result.select_one("a.result__a")
            if anchor is None:
                continue
            href = anchor.get("href")
            if not isinstance(href, str):
                continue
            snippet_el = result.select_one(".result__snippet")
            hits.append(
                WebSearchHit(
                    title=anchor.get_text(" ", strip=True),
                    url=_resolve_redirect(href),
                    snippet=snippet_el.get_text(" ", strip=True) if snippet_el else "",
                    score=round(max(0.1, 1.0 - rank * _RANK_DECAY), 4),
                )
            )
            if len(hits) >= max_results:
                break
        return hits


def _resolve_redirect(href: str) -> str:
    """DDG는 결과 링크를 //duckduckgo.com/l/?uddg=<원본URL> 형태로 감싼다."""
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [])
        if target:
            return unquote(target[0])
    return href

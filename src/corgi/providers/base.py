"""외부 연동 추상화 계층.

Protocol은 Java의 interface에 대응하지만 "구조적 타이핑"이다:
implements 선언 없이도 메서드 시그니처만 맞으면 구현체로 인정된다
(테스트에서 Fake 객체를 끼워 넣기 쉬운 이유).
"""

from dataclasses import dataclass
from typing import Protocol


# frozen=True: 불변 객체 (Java record에 대응), slots=True: 메모리/오타 방지
@dataclass(frozen=True, slots=True)
class WebSearchHit:
    """검색엔진이 돌려주는 원시 검색 결과 한 건."""

    title: str
    url: str
    snippet: str
    score: float


@dataclass(frozen=True, slots=True)
class CrawledPage:
    """크롤러가 URL 하나에서 추출한 콘텐츠."""

    url: str
    title: str
    text: str
    markdown: str
    image_urls: tuple[str, ...] = ()
    favicon: str | None = None
    # 사이트 크롤링(BFS)에서 다음에 방문할 후보 링크. extract 엔드포인트는 무시한다.
    links: tuple[str, ...] = ()


class SearchProvider(Protocol):
    async def search(self, query: str, *, max_results: int) -> list[WebSearchHit]: ...


class Crawler(Protocol):
    async def fetch(self, url: str, *, timeout: float | None = None) -> CrawledPage: ...

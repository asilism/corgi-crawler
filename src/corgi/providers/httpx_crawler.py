"""httpx + BeautifulSoup 기반 크롤러.

본문 텍스트/간이 마크다운을 추출한다. 완전한 HTML→Markdown 변환기는 아니며
제목/문단/리스트 수준의 구조만 보존한다 (Tavily raw_content 용도로 충분).
"""

import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from corgi.providers.base import CrawledPage

# 본문과 무관한 보일러플레이트 태그들
_STRIP_TAGS = ("script", "style", "noscript", "template", "header", "footer", "nav", "aside")
_BLANK_LINES = re.compile(r"\n{3,}")


class HttpxCrawler:
    def __init__(self, client: httpx.AsyncClient, *, default_timeout: float) -> None:
        self._client = client
        self._default_timeout = default_timeout

    async def fetch(self, url: str, *, timeout: float | None = None) -> CrawledPage:
        response = await self._client.get(
            url,
            timeout=timeout if timeout is not None else self._default_timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
        return self._extract(str(response.url), response.text)

    def _extract(self, url: str, html: str) -> CrawledPage:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(_STRIP_TAGS):
            tag.decompose()  # 트리에서 제거 (파괴적 연산)

        title = soup.title.get_text(strip=True) if soup.title else url
        text = _BLANK_LINES.sub("\n\n", soup.get_text("\n", strip=True))
        markdown = self._to_markdown(soup, title)
        return CrawledPage(
            url=url,
            title=title,
            text=text,
            markdown=markdown,
            image_urls=self._collect_images(soup, base_url=url),
            favicon=self._find_favicon(soup, base_url=url),
        )

    @staticmethod
    def _to_markdown(soup: BeautifulSoup, title: str) -> str:
        lines: list[str] = [f"# {title}", ""]
        for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre"]):
            content = element.get_text(" ", strip=True)
            if not content:
                continue
            name = element.name or ""
            if name.startswith("h"):
                lines.append(f"{'#' * int(name[1])} {content}")
            elif name == "li":
                lines.append(f"- {content}")
            elif name == "pre":
                lines.append(f"```\n{content}\n```")
            else:
                lines.append(content)
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def _collect_images(soup: BeautifulSoup, *, base_url: str) -> tuple[str, ...]:
        urls: list[str] = []
        for img in soup.find_all("img"):
            src = img.get("src")
            if isinstance(src, str) and src and not src.startswith("data:"):
                urls.append(urljoin(base_url, src))
        # dict.fromkeys: 순서를 유지하면서 중복 제거하는 파이썬 관용구
        return tuple(dict.fromkeys(urls))

    @staticmethod
    def _find_favicon(soup: BeautifulSoup, *, base_url: str) -> str | None:
        link = soup.find("link", rel=lambda value: bool(value) and "icon" in str(value).lower())
        if isinstance(link, Tag):
            href = link.get("href")
            if isinstance(href, str) and href:
                return urljoin(base_url, href)
        return urljoin(base_url, "/favicon.ico")

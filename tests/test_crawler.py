"""SiteCrawler(BFS 사이트 크롤러) 테스트. 네트워크는 MockTransport로 대체."""

import httpx

from corgi.indexing.crawler import SiteCrawler
from corgi.providers.httpx_crawler import HttpxCrawler

# 서로 링크된 미니 사이트. /a -> /c 로 한 단계 더 들어간다.
SITE = {
    "/": (
        "<html><head><title>Home</title></head><body>"
        '<a href="/a">A</a><a href="/b">B</a>'
        '<a href="https://other.example.org/x">External</a>'
        "</body></html>"
    ),
    "/a": (
        '<html><head><title>A</title></head><body><p>corgi a</p><a href="/c">C</a></body></html>'
    ),
    "/b": "<html><head><title>B</title></head><body><p>corgi b</p></body></html>",
    "/c": "<html><head><title>C</title></head><body><p>corgi c</p></body></html>",
    "/robots.txt": "User-agent: *\nDisallow: /b\n",
}


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.host != "site.example.com":
        return httpx.Response(200, text="<html><title>ext</title><body>external</body></html>")
    body = SITE.get(request.url.path)
    if body is None:
        return httpx.Response(404, text="not found")
    return httpx.Response(200, text=body)


def _make_crawler(client: httpx.AsyncClient, **overrides: object) -> SiteCrawler:
    params: dict[str, object] = {
        "allowed_domains": ("site.example.com",),
        "max_depth": 1,
        "max_pages": 100,
        "delay": 0.0,
        "user_agent": "CorgiTest",
        "respect_robots": True,
    }
    params.update(overrides)
    return SiteCrawler(HttpxCrawler(client, default_timeout=5.0), client, **params)  # type: ignore[arg-type]


async def test_bfs_respects_depth_robots_and_domain() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        crawler = _make_crawler(client)
        pages = [page async for page in crawler.crawl(["https://site.example.com/"])]

    urls = {page.url for page in pages}
    # home(depth0) + /a(depth1)만. /b는 robots Disallow, /c는 depth2라 제외,
    # external 도메인도 제외된다.
    assert urls == {"https://site.example.com/", "https://site.example.com/a"}


async def test_max_pages_caps_crawl() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        crawler = _make_crawler(client, max_pages=1)
        pages = [page async for page in crawler.crawl(["https://site.example.com/"])]
    assert len(pages) == 1


async def test_ignoring_robots_visits_disallowed_path() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        crawler = _make_crawler(client, respect_robots=False)
        pages = [page async for page in crawler.crawl(["https://site.example.com/"])]
    urls = {page.url for page in pages}
    # robots를 무시하면 /b도 방문한다
    assert "https://site.example.com/b" in urls


async def test_deeper_crawl_reaches_grandchild() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        crawler = _make_crawler(client, max_depth=2, respect_robots=False)
        pages = [page async for page in crawler.crawl(["https://site.example.com/"])]
    urls = {page.url for page in pages}
    # depth2까지 가면 /a 가 링크한 /c 도 방문
    assert "https://site.example.com/c" in urls

"""provider 단위 테스트 (HTTP 레벨은 httpx MockTransport로 대체)."""

import httpx
import pytest

from corgi.core.exceptions import UpstreamError
from corgi.providers.duckduckgo import DuckDuckGoSearchProvider, _resolve_redirect
from corgi.providers.httpx_crawler import HttpxCrawler

DDG_HTML = """
<html><body>
  <div class="result">
    <a class="result__a"
       href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdogs.example.com%2Fcorgi&rut=abc"
    >Corgi facts</a>
    <a class="result__snippet">Corgis are small herding dogs.</a>
  </div>
  <div class="result">
    <a class="result__a" href="https://example.org/direct">Direct link</a>
  </div>
</body></html>
"""

PAGE_HTML = """
<html>
  <head>
    <title>Corgi facts</title>
    <link rel="shortcut icon" href="/static/favicon.png">
    <script>tracking();</script>
  </head>
  <body>
    <nav>Home | About</nav>
    <h1>Corgi facts</h1>
    <p>Corgis are small herding dogs.</p>
    <ul><li>Short legs</li></ul>
    <img src="/corgi.jpg">
  </body>
</html>
"""


def _client_returning(html: str) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_resolve_redirect_unwraps_ddg_link() -> None:
    wrapped = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fdogs.example.com%2Fcorgi&rut=abc"
    assert _resolve_redirect(wrapped) == "https://dogs.example.com/corgi"
    assert _resolve_redirect("https://example.org/direct") == "https://example.org/direct"


async def test_duckduckgo_parsing() -> None:
    provider = DuckDuckGoSearchProvider(_client_returning(DDG_HTML))
    hits = await provider.search("corgi", max_results=5)

    assert len(hits) == 2
    assert hits[0].title == "Corgi facts"
    assert hits[0].url == "https://dogs.example.com/corgi"
    assert hits[0].snippet == "Corgis are small herding dogs."
    assert hits[0].score > hits[1].score  # 순위가 높을수록 점수가 높다


async def test_duckduckgo_zero_max_results() -> None:
    provider = DuckDuckGoSearchProvider(_client_returning(DDG_HTML))
    assert await provider.search("corgi", max_results=0) == []


async def test_duckduckgo_upstream_failure_raises_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    provider = DuckDuckGoSearchProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(UpstreamError):
        await provider.search("corgi", max_results=5)


async def test_crawler_extraction() -> None:
    crawler = HttpxCrawler(_client_returning(PAGE_HTML), default_timeout=5.0)
    page = await crawler.fetch("https://dogs.example.com/corgi")

    assert page.title == "Corgi facts"
    # script/nav 등 보일러플레이트는 제거되어야 한다
    assert "tracking" not in page.text
    assert "Home | About" not in page.text
    assert "Corgis are small herding dogs." in page.text
    assert "# Corgi facts" in page.markdown
    assert "- Short legs" in page.markdown
    assert page.image_urls == ("https://dogs.example.com/corgi.jpg",)
    assert page.favicon == "https://dogs.example.com/static/favicon.png"

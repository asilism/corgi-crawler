"""애플리케이션 엔트리포인트.

실행: uvicorn corgi.main:app --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from corgi.core.config import get_settings
from corgi.core.exceptions import register_exception_handlers
from corgi.routers import extract, search


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """앱 기동/종료 훅. Spring의 @PostConstruct/@PreDestroy에 대응."""
    settings = get_settings()
    async with httpx.AsyncClient(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.http_timeout,
    ) as client:
        app.state.http_client = client
        yield  # 여기서 앱이 서비스되고, 종료 시 client가 정리된다


def create_app() -> FastAPI:
    # 팩토리 함수로 만들면 테스트마다 독립된 앱 인스턴스를 쓸 수 있다
    app = FastAPI(
        title="Corgi",
        description="Tavily 호환 웹 검색/크롤링 API",
        version="0.1.0",
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.include_router(search.router)
    app.include_router(extract.router)
    return app


app = create_app()

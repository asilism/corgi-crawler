# Corgi 🐕

Tavily API와 동일한 스펙(엔드포인트, 요청/응답 스키마, 인증)을 따르는
웹 검색·크롤링 백엔드. 기존 Tavily 클라이언트에서 base_url만 바꾸면
그대로 동작하는 drop-in 호환을 목표로 한다.

```python
from tavily import TavilyClient

client = TavilyClient(api_key="your-key")
client.base_url = "http://localhost:8000"   # 이것만 바꾸면 끝
client.search("when was the corgi breed established?")
```

## 실행

```bash
uv sync                                  # 의존성 설치
uv run uvicorn corgi.main:app --reload   # http://localhost:8000/docs
```

## 설정 (환경변수 또는 .env)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `CORGI_API_KEYS` | (빈 값) | 쉼표로 구분된 허용 API 키. 비어 있으면 인증 비활성(개발 모드) |
| `CORGI_HTTP_TIMEOUT` | `10.0` | 외부 HTTP 요청 타임아웃(초) |
| `CORGI_MAX_CONCURRENT_FETCHES` | `8` | 크롤링 동시 요청 수 제한 |

## API

### POST /search — 웹 검색

```bash
curl -X POST http://localhost:8000/search \
  -H "Authorization: Bearer <key>" \
  -H "Content-Type: application/json" \
  -d '{"query": "corgi", "max_results": 5, "include_answer": true}'
```

응답: `query`, `answer`, `results[]`(`title`, `url`, `content`, `score`,
`raw_content`), `response_time`, `request_id`

### POST /extract — URL 본문 추출

```bash
curl -X POST http://localhost:8000/extract \
  -H "Authorization: Bearer <key>" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://en.wikipedia.org/wiki/Welsh_Corgi"], "format": "markdown"}'
```

응답: `results[]`(`url`, `raw_content`), `failed_results[]`(`url`, `error`),
`response_time`, `request_id`

인증은 `Authorization: Bearer` 헤더(현행)와 요청 바디 `api_key` 필드
(구버전 클라이언트) 둘 다 지원한다.

## 아키텍처 (Spring MVC 대응)

| 디렉터리 | Spring 대응 | 역할 |
|---|---|---|
| `routers/` | `@RestController` | 라우팅, 인증 확인, 서비스 위임 |
| `schemas/` | DTO | Pydantic 요청/응답 모델 (Tavily 스펙 그대로) |
| `services/` | `@Service` | 검색/추출 비즈니스 로직 |
| `providers/` | 외부 연동 어댑터 | `SearchProvider`/`Crawler` 인터페이스(Protocol)와 구현체 |
| `core/` | `@Configuration` 등 | 설정, 인증, 예외 핸들러, DI 조립(Depends) |

검색엔진은 기본으로 DuckDuckGo HTML(키 불필요)을 쓰며,
`providers/base.py`의 `SearchProvider` 프로토콜만 만족하면
다른 엔진(Google CSE, Bing, SearxNG 등)으로 교체할 수 있다.

### Tavily와의 의도적 차이

- `answer`는 LLM이 아닌 상위 결과 스니펫을 이어 붙인 추출형 요약이다
  (`services/search_service.py`의 `_compose_answer`만 교체하면 LLM 연동 가능).
- `topic`, `time_range`, `country` 등 일부 파라미터는 스키마로는 받지만
  아직 검색 동작에 반영하지 않는다 (요청 호환성 유지 목적).

## 개발

```bash
uv run pytest          # 테스트
uv run ruff check .    # lint
uv run ruff format .   # format
uv run mypy            # 타입 체크 (strict)
```

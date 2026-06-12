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
| `CORGI_SEARCH_BACKEND` | `duckduckgo` | 검색 백엔드: `duckduckgo`(외부 빌림) 또는 `index`(자체 색인) |
| `CORGI_INDEX_PATH` | `corgi_index.db` | 자체 색인 SQLite 파일 경로 |
| `CORGI_CRAWL_SEEDS` | (빈 값) | 쉼표로 구분된 크롤 시드 URL |
| `CORGI_CRAWL_MAX_DEPTH` | `2` | 시드에서 따라갈 링크 깊이 |
| `CORGI_CRAWL_MAX_PAGES` | `100` | 크롤할 최대 페이지 수 |
| `CORGI_CRAWL_DELAY` | `0.5` | 요청 간 예의상 지연(초) |
| `CORGI_CRAWL_RESPECT_ROBOTS` | `true` | robots.txt 준수 여부 |

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

## 검색 백엔드: 빌리기 vs. 자체 색인

`/search`는 두 가지 백엔드를 지원한다 (`CORGI_SEARCH_BACKEND`).

**① `duckduckgo` (기본)** — DuckDuckGo HTML 결과를 파싱해 쓴다. 키도
과금도 없지만, 본질적으로 "남의 인덱스를 빌리는" 것이라 rate limit·차단
위험이 있고 운영 트래픽에는 부적합하다.

**② `index` — 자체 크롤·색인** — 우리가 직접 도메인을 크롤링해 SQLite
FTS5 인덱스에 색인하고, BM25 랭킹으로 검색한다. 외부 검색엔진에 의존하지
않는다 (Tavily가 내부적으로 갖는 인덱스의 축소판). 별도 검색 서버
(Elasticsearch 등)가 필요 없고 표준 라이브러리만으로 동작한다.

```bash
# 1) 시드 도메인을 크롤링해 인덱스 구축
export CORGI_CRAWL_SEEDS="https://example.com,https://docs.example.com"
uv run corgi-crawl                       # corgi_index.db 생성

# 2) 인덱스 백엔드로 서버 기동
export CORGI_SEARCH_BACKEND=index
uv run uvicorn corgi.main:app
```

크롤러는 시드 호스트(및 서브도메인) 안에만 머물고, `robots.txt`를 준수하며,
깊이·페이지 수 상한과 요청 간 지연을 지킨다. 임베딩(벡터) 검색을 얹고
싶으면 `providers/sqlite_index.py` 뒤에 하이브리드 랭킹 레이어를 추가하면
된다 — 인터페이스(`SearchProvider`)는 그대로다.

> 참고: 현재 `index` 백엔드에서 `include_raw_content=true`는 색인된 본문을
> 재사용하지 않고 원본 URL을 다시 크롤링한다. 색인 본문을 바로 반환하도록
> 최적화하는 것은 향후 과제.

## 아키텍처 (Spring MVC 대응)

| 디렉터리 | Spring 대응 | 역할 |
|---|---|---|
| `routers/` | `@RestController` | 라우팅, 인증 확인, 서비스 위임 |
| `schemas/` | DTO | Pydantic 요청/응답 모델 (Tavily 스펙 그대로) |
| `services/` | `@Service` | 검색/추출 비즈니스 로직 |
| `providers/` | 외부 연동 어댑터 | `SearchProvider`/`Crawler` 인터페이스(Protocol)와 구현체 (DDG, SQLite 인덱스) |
| `indexing/` | `@Scheduled` 배치 잡 | 오프라인 크롤·색인 (`corgi-crawl` CLI) |
| `core/` | `@Configuration` 등 | 설정, 인증, 예외 핸들러, DI 조립(Depends) |

`providers/base.py`의 `SearchProvider` 프로토콜만 만족하면 검색 백엔드를
교체할 수 있다 — DuckDuckGo, 자체 SQLite 인덱스, 혹은 다른 엔진
(Google CSE, Brave, SearxNG 등) 모두 같은 인터페이스 뒤에 꽂힌다.

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

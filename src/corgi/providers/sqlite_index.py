"""SQLite FTS5 기반 검색 인덱스.

우리가 직접 크롤링한 페이지를 색인하고, BM25 랭킹으로 검색한다.
외부 검색엔진(DDG/Bing)에 의존하지 않는 "자체 인덱스" 구현 — Tavily가
내부적으로 갖는 인덱스의 축소판이다.

FTS5는 SQLite에 내장된 전문(full-text) 역색인 확장으로, 별도 서버
(Elasticsearch 등) 없이 BM25 랭킹 검색을 제공한다. 임베딩(벡터) 검색을
얹고 싶으면 이 클래스 뒤에 하이브리드 랭킹 레이어를 추가하면 된다.
"""

import asyncio
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from corgi.core.exceptions import UpstreamError
from corgi.providers.base import WebSearchHit

# 외부 콘텐츠(external content) FTS5 패턴: 원본은 pages 테이블에 두고
# pages_fts는 색인만 담는다. 트리거로 둘을 동기화한다 (SQLite 공식 권장 패턴).
_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id      INTEGER PRIMARY KEY,
    url     TEXT UNIQUE NOT NULL,
    title   TEXT NOT NULL,
    content TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    title, content,
    content='pages', content_rowid='id', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
    INSERT INTO pages_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
END;
CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, title, content)
        VALUES ('delete', old.id, old.title, old.content);
END;
CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, title, content)
        VALUES ('delete', old.id, old.title, old.content);
    INSERT INTO pages_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
END;
"""

_SEARCH_SQL = """
SELECT
    p.url,
    p.title,
    CASE
        WHEN snippet(pages_fts, 1, '', '', ' … ', 20) = ''
        THEN substr(p.content, 1, 200)
        ELSE snippet(pages_fts, 1, '', '', ' … ', 20)
    END AS excerpt,
    bm25(pages_fts) AS rank
FROM pages_fts
JOIN pages p ON p.id = pages_fts.rowid
WHERE pages_fts MATCH ?
ORDER BY rank
LIMIT ?
"""

# FTS5 쿼리 문법 특수문자를 피하기 위해 단어 토큰만 뽑는다 (한글/영문/숫자)
_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class IndexedDocument:
    url: str
    title: str
    content: str


def _to_match_query(query: str) -> str | None:
    """사용자 입력을 안전한 FTS5 MATCH 문자열로 변환한다.

    각 단어를 큰따옴표로 감싸 특수문자 주입을 막고, OR로 이어 재현율을
    높인다 (정밀도는 BM25 랭킹이 보정). 토큰이 없으면 None.
    """
    terms = _WORD.findall(query)
    if not terms:
        return None
    return " OR ".join(f'"{term}"' for term in terms)


class SqliteIndex:
    """SearchProvider 프로토콜 구현 + 색인 쓰기 기능.

    연결은 작업 단위로 열고 닫는다. 읽기는 asyncio.to_thread로 워커 스레드에서
    수행하므로, 매번 새 연결을 여는 편이 스레드 안전 측면에서 가장 단순하다.
    """

    def __init__(self, path: str) -> None:
        self._path = path

    def initialize(self) -> None:
        """스키마를 생성한다 (이미 있으면 무시). 크롤 전에 한 번 호출."""
        conn = sqlite3.connect(self._path)
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        except sqlite3.OperationalError as exc:  # FTS5 미컴파일 빌드 등
            raise RuntimeError(
                f"SQLite FTS5를 초기화하지 못했습니다 (FTS5 미지원 빌드?): {exc}"
            ) from exc
        finally:
            conn.close()

    def upsert_many(self, documents: list[IndexedDocument]) -> None:
        """URL 기준 upsert. 같은 URL은 최신 내용으로 덮어쓴다.

        FTS5 외부 콘텐츠 테이블은 ON CONFLICT 업서트가 까다로우므로
        '삭제 후 삽입'으로 처리한다 (트리거가 색인을 동기화).
        """
        conn = sqlite3.connect(self._path)
        try:
            for doc in documents:
                conn.execute("DELETE FROM pages WHERE url = ?", (doc.url,))
                conn.execute(
                    "INSERT INTO pages (url, title, content) VALUES (?, ?, ?)",
                    (doc.url, doc.title, doc.content),
                )
            conn.commit()
        finally:
            conn.close()

    def count(self) -> int:
        conn = sqlite3.connect(self._path)
        try:
            row = conn.execute("SELECT count(*) FROM pages").fetchone()
            return int(row[0])
        finally:
            conn.close()

    async def search(self, query: str, *, max_results: int) -> list[WebSearchHit]:
        if max_results <= 0:
            return []
        match = _to_match_query(query)
        if match is None:
            return []
        # 블로킹 sqlite 호출을 이벤트 루프 밖(스레드)에서 실행
        return await asyncio.to_thread(self._search_sync, match, max_results)

    def _search_sync(self, match: str, limit: int) -> list[WebSearchHit]:
        if not Path(self._path).exists():
            raise UpstreamError("검색 인덱스가 없습니다. 먼저 `corgi-crawl`로 색인하세요.")
        # 읽기 전용 연결 (uri=True). 쓰기 배치와 충돌하지 않는다.
        conn = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
        try:
            rows = conn.execute(_SEARCH_SQL, (match, limit)).fetchall()
        except sqlite3.OperationalError as exc:
            raise UpstreamError(f"인덱스 조회 실패: {exc}") from exc
        finally:
            conn.close()
        return _rows_to_hits(rows)


# 매칭된 결과가 0점으로 표시되지 않도록 점수를 이 구간으로 정규화한다
_SCORE_FLOOR = 0.1
_SCORE_CEIL = 1.0


def _rows_to_hits(rows: list[tuple[str, str, str, float]]) -> list[WebSearchHit]:
    """BM25 점수를 [0.1, 1.0] 상대 점수로 정규화한다 (Tavily score 호환).

    SQLite bm25()는 '작을수록(더 음수일수록) 관련도 높음'이라 부호를 뒤집어
    관련도(클수록 좋음)로 만든 뒤 min-max 정규화한다. 최상위는 1.0, 최하위
    매칭은 0.1 — 매칭된 결과가 0.0으로 보이는 오해를 피하기 위해 바닥을 둔다.
    """
    if not rows:
        return []
    relevances = [-rank for (_, _, _, rank) in rows]
    hi, lo = max(relevances), min(relevances)
    span = hi - lo
    hits: list[WebSearchHit] = []
    for (url, title, excerpt, _), relevance in zip(rows, relevances, strict=True):
        if span > 0:
            score = round(_SCORE_FLOOR + (_SCORE_CEIL - _SCORE_FLOOR) * (relevance - lo) / span, 4)
        else:  # 결과가 하나거나 점수가 모두 같으면 최상위로 본다
            score = _SCORE_CEIL
        hits.append(WebSearchHit(title=title, url=url, snippet=excerpt, score=score))
    return hits

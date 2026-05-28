"""RAG 벡터 저장소 — Supabase Postgres + pgvector.

기존 ChromaDB에서 이전. 호출부 변경 최소화를 위해 Chroma 컬렉션과 동일한
메서드 시그니처(count/query/add/upsert/get/delete)를 제공하는 drop-in 래퍼.

- 단일 테이블 rag_vectors, collection 컬럼으로 trusted/user_uploads 구분
- 임베딩은 gemini-embedding-001 (3072차원). 코퍼스가 모뎀 규모라 인덱스 없이
  정확 검색(cosine <=>)으로 충분. 대규모 되면 halfvec+hnsw 추가.
"""
from functools import lru_cache

from pgvector import Vector
from pgvector.psycopg import register_vector

from app.db.trade_db import _get_pool
from app.llm.gemini import embed_texts

TRUSTED_COLLECTION = "trusted"
USER_UPLOADS_COLLECTION = "user_uploads"

EMBED_DIM = 3072
_initialized = False


def _ensure_schema() -> None:
    global _initialized
    if _initialized:
        return
    pool = _get_pool()
    with pool.connection() as con:
        con.execute("CREATE EXTENSION IF NOT EXISTS vector")
        con.execute(
            f"""CREATE TABLE IF NOT EXISTS rag_vectors (
                id          TEXT NOT NULL,
                collection  TEXT NOT NULL,
                document    TEXT NOT NULL,
                metadata    JSONB,
                embedding   vector({EMBED_DIM}),
                PRIMARY KEY (collection, id)
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_rag_collection ON rag_vectors(collection)")
        # 구버전(단일 id PK) 교정 — 단일 컬럼 PK일 때만 1회 (idempotent)
        try:
            con.execute("""
                DO $$
                DECLARE n int;
                BEGIN
                  SELECT array_length(i.indkey::int[], 1) INTO n FROM pg_index i
                    WHERE i.indrelid = 'rag_vectors'::regclass AND i.indisprimary;
                  IF n = 1 THEN
                    ALTER TABLE rag_vectors DROP CONSTRAINT rag_vectors_pkey;
                    ALTER TABLE rag_vectors ADD PRIMARY KEY (collection, id);
                  END IF;
                END $$;
            """)
        except Exception:
            pass
    _initialized = True


def _register(con):
    register_vector(con)


def _where_sql(collection: str, where: dict | None) -> tuple[str, list]:
    """collection + metadata 필터 → (WHERE 절, params)."""
    clauses = ["collection = %s"]
    params: list = [collection]
    if where:
        for k, v in where.items():
            clauses.append("metadata->>%s = %s")
            params.append(k)
            params.append(str(v))
    return " AND ".join(clauses), params


class PgVectorCollection:
    """ChromaDB 컬렉션 인터페이스 호환 래퍼."""

    def __init__(self, name: str):
        self.name = name
        _ensure_schema()

    def count(self) -> int:
        with _get_pool().connection() as con:
            row = con.execute(
                "SELECT count(*) AS c FROM rag_vectors WHERE collection = %s",
                (self.name,),
            ).fetchone()
        return row["c"] if row else 0

    def add(self, documents: list[str], ids: list[str], metadatas: list[dict] | None = None) -> None:
        self._write(documents, ids, metadatas, upsert=False)

    def upsert(self, documents: list[str], ids: list[str], metadatas: list[dict] | None = None) -> None:
        self._write(documents, ids, metadatas, upsert=True)

    def _write(self, documents, ids, metadatas, upsert: bool) -> None:
        import json as _json
        if not documents:
            return
        metadatas = metadatas or [{} for _ in documents]
        vectors = embed_texts(list(documents))
        rows = [
            (ids[i], self.name, documents[i], _json.dumps(metadatas[i], ensure_ascii=False), Vector(vectors[i]))
            for i in range(len(documents))
        ]
        conflict = (
            "ON CONFLICT(collection, id) DO UPDATE SET document=excluded.document, "
            "metadata=excluded.metadata, embedding=excluded.embedding"
            if upsert else "ON CONFLICT(collection, id) DO NOTHING"
        )
        with _get_pool().connection() as con:
            _register(con)
            con.cursor().executemany(
                f"""INSERT INTO rag_vectors (id, collection, document, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s) {conflict}""",
                rows,
            )

    def query(self, query_texts: list[str], n_results: int = 5) -> dict:
        """ChromaDB query 형식 반환: {documents:[[...]], metadatas:[[...]], distances:[[...]]}."""
        qvec = embed_texts(list(query_texts))[0]
        with _get_pool().connection() as con:
            _register(con)
            rows = con.execute(
                """SELECT document, metadata, embedding <=> %s AS dist
                   FROM rag_vectors WHERE collection = %s
                   ORDER BY dist LIMIT %s""",
                (Vector(qvec), self.name, n_results),
            ).fetchall()
        docs = [r["document"] for r in rows]
        metas = [r["metadata"] or {} for r in rows]
        dists = [float(r["dist"]) for r in rows]
        # Chroma는 쿼리별로 한 겹 더 감싼 nested list
        return {"documents": [docs], "metadatas": [metas], "distances": [dists]}

    def get(self, where: dict | None = None, limit: int | None = None, include: list | None = None) -> dict:
        """ChromaDB get 형식 반환: {ids:[...], documents:[...], metadatas:[...]} (flat)."""
        where_sql, params = _where_sql(self.name, where)
        sql = f"SELECT id, document, metadata FROM rag_vectors WHERE {where_sql}"
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)
        with _get_pool().connection() as con:
            rows = con.execute(sql, params).fetchall()
        return {
            "ids": [r["id"] for r in rows],
            "documents": [r["document"] for r in rows],
            "metadatas": [r["metadata"] or {} for r in rows],
        }

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        placeholders = ",".join(["%s"] * len(ids))
        with _get_pool().connection() as con:
            con.execute(
                f"DELETE FROM rag_vectors WHERE collection = %s AND id IN ({placeholders})",
                [self.name, *ids],
            )


@lru_cache(maxsize=4)
def _get_collection(name: str) -> PgVectorCollection:
    return PgVectorCollection(name)


def get_trusted_collection() -> PgVectorCollection:
    return _get_collection(TRUSTED_COLLECTION)


def get_user_uploads_collection() -> PgVectorCollection:
    return _get_collection(USER_UPLOADS_COLLECTION)

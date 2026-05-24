from functools import lru_cache
from pathlib import Path
from typing import cast

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from chromadb.config import Settings as ChromaSettings

from app.llm.gemini import embed_texts

CHROMA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "chroma"
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

TRUSTED_COLLECTION = "trusted"
USER_UPLOADS_COLLECTION = "user_uploads"


class GeminiEmbeddingFunction(EmbeddingFunction[Documents]):
    """Chroma 컬렉션이 add/query 시 호출하는 임베딩 함수."""

    def __call__(self, input: Documents) -> Embeddings:
        vectors = embed_texts(list(input))
        return cast(Embeddings, vectors)


@lru_cache(maxsize=1)
def _client() -> chromadb.api.ClientAPI:
    return chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def _get_collection(name: str, description: str):
    return _client().get_or_create_collection(
        name=name,
        embedding_function=GeminiEmbeddingFunction(),
        metadata={"description": description},
    )


def get_trusted_collection():
    return _get_collection(TRUSTED_COLLECTION, "공식 데이터 (DART·뉴스·KRX 등)")


def get_user_uploads_collection():
    return _get_collection(USER_UPLOADS_COLLECTION, "유저 업로드 자료 (검증 대상)")

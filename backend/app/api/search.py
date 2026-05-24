from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.chroma_client import get_user_uploads_collection

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="검색 질의")
    n_results: int = Field(default=5, ge=1, le=20)
    upload_id: str | None = Field(default=None, description="특정 업로드 파일로 제한")


class SearchMatch(BaseModel):
    text: str
    distance: float
    metadata: dict


class SearchResponse(BaseModel):
    query: str
    matches: list[SearchMatch]


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    if not req.query.strip():
        raise HTTPException(400, "검색어를 입력해주세요")

    collection = get_user_uploads_collection()
    if collection.count() == 0:
        return SearchResponse(query=req.query, matches=[])

    try:
        where = {"upload_id": req.upload_id} if req.upload_id else None
        results = collection.query(
            query_texts=[req.query],
            n_results=req.n_results,
            where=where,
        )
    except Exception as e:
        raise HTTPException(500, f"검색 실패: {type(e).__name__}: {e}")

    documents = results.get("documents", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    matches = [
        SearchMatch(text=doc, distance=dist, metadata=meta or {})
        for doc, dist, meta in zip(documents, distances, metadatas)
    ]
    return SearchResponse(query=req.query, matches=matches)

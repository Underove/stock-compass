import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.auth import get_current_user
from app.db.chroma_client import get_user_uploads_collection
from app.db.storage import delete_original, get_download_url, upload_original
from app.parsers.pdf_parser import chunk_text, extract_text_from_pdf

router = APIRouter()

ALLOWED_EXTENSIONS = (".pdf", ".txt")
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB
KOREAN_ENCODINGS = ("utf-8", "cp949", "euc-kr")


def _decode_text(content: bytes) -> str:
    for encoding in KOREAN_ENCODINGS:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _extract_pdf_bytes(content: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        return extract_text_from_pdf(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _store_in_vector_db(
    chunks: list[str],
    upload_id: str,
    filename: str,
    username: str,
    storage_path: str | None = None,
) -> tuple[bool, str | None]:
    """벡터 저장 성공 시 (True, None), 실패 시 (False, error message)."""
    try:
        collection = get_user_uploads_collection()
        now = datetime.now(timezone.utc).isoformat()
        collection.add(
            documents=chunks,
            ids=[f"{upload_id}_{i}" for i in range(len(chunks))],
            metadatas=[
                {
                    "upload_id": upload_id,
                    "username": username,
                    "filename": filename,
                    "uploaded_at": now,
                    "chunk_index": i,
                    "source_type": "user_upload",
                    "storage_path": storage_path or "",
                }
                for i in range(len(chunks))
            ],
        )
        return True, None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


@router.get("/uploads")
def list_uploads(username: str = Depends(get_current_user)) -> dict:
    """본인 업로드 자료 목록 반환 (upload_id별 deduplicate)."""
    collection = get_user_uploads_collection()
    result = collection.get(where={"username": username}, include=["metadatas"])
    metadatas = result.get("metadatas") or []

    seen: dict[str, dict] = {}
    for meta in metadatas:
        uid = meta.get("upload_id")
        if not uid:
            continue
        if uid not in seen:
            seen[uid] = {
                "upload_id": uid,
                "filename": meta.get("filename", ""),
                "uploaded_at": meta.get("uploaded_at", ""),
                "chunk_count": 0,
            }
        seen[uid]["chunk_count"] += 1

    uploads = sorted(seen.values(), key=lambda x: x["uploaded_at"], reverse=True)
    return {"uploads": uploads}


@router.get("/uploads/{upload_id}/original")
def get_upload_original(upload_id: str, username: str = Depends(get_current_user)):
    """본인 업로드 원본 파일의 임시 다운로드 URL 반환 (Supabase Storage)."""
    collection = get_user_uploads_collection()
    result = collection.get(where={"upload_id": upload_id, "username": username}, include=["metadatas"])
    metas = result.get("metadatas") or []
    if not metas:
        raise HTTPException(404, "해당 자료를 찾을 수 없습니다.")
    storage_path = (metas[0] or {}).get("storage_path") or ""
    if not storage_path:
        raise HTTPException(404, "이 자료는 원본이 보관되지 않았어요.")
    url = get_download_url(storage_path)
    if not url:
        raise HTTPException(503, "원본 다운로드 링크를 만들지 못했어요.")
    return {"url": url, "filename": (metas[0] or {}).get("filename", "")}


@router.delete("/uploads/{upload_id}")
def delete_upload(upload_id: str, username: str = Depends(get_current_user)):
    """본인 upload_id의 모든 청크 + 원본 파일 삭제."""
    collection = get_user_uploads_collection()
    result = collection.get(where={"upload_id": upload_id, "username": username}, include=["metadatas"])
    ids = result.get("ids") or []
    metas = result.get("metadatas") or []
    if not ids:
        raise HTTPException(404, "해당 자료를 찾을 수 없습니다.")
    storage_path = (metas[0] or {}).get("storage_path") if metas else ""
    collection.delete(ids=ids)
    if storage_path:
        delete_original(storage_path)
    return {"ok": True, "deleted_chunks": len(ids)}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    username: str = Depends(get_current_user),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"지원하지 않는 파일 형식입니다. ({', '.join(ALLOWED_EXTENSIONS)} 만 가능)",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(413, "파일 크기가 20MB를 초과했습니다.")

    text = (_extract_pdf_bytes(content) if suffix == ".pdf" else _decode_text(content)).strip()
    if not text:
        raise HTTPException(
            422,
            "파일에서 텍스트를 추출하지 못했습니다. 스캔본일 경우 OCR이 필요합니다.",
        )

    chunks = chunk_text(text)
    upload_id = str(uuid.uuid4())

    # 원본 파일 보관 (Supabase Storage — 미설정 시 None, 기능 영향 없음)
    storage_path = upload_original(
        upload_id, file.filename or "file", content,
        file.content_type or ("application/pdf" if suffix == ".pdf" else "text/plain"),
    )

    stored, error = _store_in_vector_db(chunks, upload_id, file.filename or "", username, storage_path)

    # #4 벡터 저장 실패 시 원본 orphan 방지 — 보상 삭제
    if not stored and storage_path:
        delete_original(storage_path)
        storage_path = None

    return {
        "upload_id": upload_id,
        "filename": file.filename or "",
        "size_bytes": len(content),
        "char_count": len(text),
        "chunk_count": len(chunks),
        "vector_db_stored": stored,
        "vector_db_error": error,
        "original_stored": storage_path is not None,
        "preview": text[:600],
        "first_chunks": chunks[:3],
    }

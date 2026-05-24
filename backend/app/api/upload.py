import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.db.chroma_client import get_user_uploads_collection
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
) -> tuple[bool, str | None]:
    """Chroma 저장 성공 시 (True, None), 실패 시 (False, error message)."""
    try:
        collection = get_user_uploads_collection()
        now = datetime.now(timezone.utc).isoformat()
        collection.add(
            documents=chunks,
            ids=[f"{upload_id}_{i}" for i in range(len(chunks))],
            metadatas=[
                {
                    "upload_id": upload_id,
                    "filename": filename,
                    "uploaded_at": now,
                    "chunk_index": i,
                    "source_type": "user_upload",
                }
                for i in range(len(chunks))
            ],
        )
        return True, None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


@router.get("/uploads")
def list_uploads() -> dict:
    """저장된 모든 업로드 자료 목록 반환 (upload_id별 deduplicate)."""
    collection = get_user_uploads_collection()
    result = collection.get(include=["metadatas"])
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


@router.delete("/uploads/{upload_id}")
def delete_upload(upload_id: str):
    """upload_id에 해당하는 모든 청크를 Chroma에서 삭제."""
    collection = get_user_uploads_collection()
    result = collection.get(where={"upload_id": upload_id}, include=["metadatas"])
    ids = result.get("ids") or []
    if not ids:
        raise HTTPException(404, "해당 자료를 찾을 수 없습니다.")
    collection.delete(ids=ids)
    return {"ok": True, "deleted_chunks": len(ids)}


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
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
    stored, error = _store_in_vector_db(chunks, upload_id, file.filename or "")

    return {
        "upload_id": upload_id,
        "filename": file.filename or "",
        "size_bytes": len(content),
        "char_count": len(text),
        "chunk_count": len(chunks),
        "vector_db_stored": stored,
        "vector_db_error": error,
        "preview": text[:600],
        "first_chunks": chunks[:3],
    }

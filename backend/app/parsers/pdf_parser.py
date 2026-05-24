from pathlib import Path

import pdfplumber


def extract_text_from_pdf(file_path: str | Path) -> str:
    """PDF 파일에서 모든 페이지 텍스트를 추출해 하나의 문자열로 반환."""
    text_parts: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts).strip()


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """텍스트를 chunk_size 글자 단위로 자르되 overlap 글자만큼 겹쳐서 반환."""
    if not text:
        return []
    if overlap >= chunk_size:
        raise ValueError("overlap은 chunk_size보다 작아야 합니다")

    step = chunk_size - overlap
    return [text[i : i + chunk_size] for i in range(0, len(text), step)]

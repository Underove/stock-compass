"""네이버 뉴스 검색 API 래퍼. NAVER_CLIENT_ID/SECRET 없으면 빈 결과 반환."""
import html
import re
from datetime import datetime

import httpx

from app.config import settings

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"


def _strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _format_date(pub_date: str) -> str:
    """'Mon, 23 Jun 2025 10:00:00 +0900' → '2025.06.23'"""
    try:
        dt = datetime.strptime(pub_date[:25], "%a, %d %b %Y %H:%M:%S")
        return dt.strftime("%Y.%m.%d")
    except Exception:
        return pub_date[:10]


def search_news(query: str, display: int = 5) -> list[dict]:
    """네이버 뉴스 검색. API 키 없으면 [] 반환."""
    if not settings.naver_client_id or not settings.naver_client_secret:
        return []
    try:
        res = httpx.get(
            NAVER_NEWS_URL,
            headers={
                "X-Naver-Client-Id": settings.naver_client_id,
                "X-Naver-Client-Secret": settings.naver_client_secret,
            },
            params={"query": query, "display": display, "sort": "date"},
            timeout=10,
        )
        res.raise_for_status()
        items = res.json().get("items", [])
        return [
            {
                "title": _strip_tags(item.get("title", "")),
                "description": _strip_tags(item.get("description", "")),
                "url": item.get("originallink") or item.get("link", ""),
                "date": _format_date(item.get("pubDate", "")),
            }
            for item in items
        ]
    except Exception:
        return []


def news_to_context(items: list[dict], label_prefix: str = "웹 뉴스") -> str:
    """뉴스 목록을 RAG 컨텍스트 문자열로 변환."""
    if not items:
        return ""
    parts = []
    for i, item in enumerate(items, start=1):
        parts.append(
            f"[{label_prefix} {i} — {item['date']}]\n"
            f"제목: {item['title']}\n"
            f"요약: {item['description']}"
        )
    return "\n\n".join(parts)

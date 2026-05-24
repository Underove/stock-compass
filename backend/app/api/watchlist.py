"""관심종목 CRUD."""
import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "watchlist.json"
_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> list[dict]:
    if not _FILE.exists():
        return []
    with open(_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save(items: list[dict]) -> None:
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


class WatchlistItem(BaseModel):
    stock_code: str
    corp_name: str


@router.get("/watchlist")
def list_watchlist():
    return {"items": _load()}


@router.post("/watchlist")
def add_watchlist(item: WatchlistItem):
    items = _load()
    if not any(i["stock_code"] == item.stock_code for i in items):
        items.append(item.model_dump())
        _save(items)
    return {"ok": True}


@router.delete("/watchlist/{stock_code}")
def remove_watchlist(stock_code: str):
    _save([i for i in _load() if i["stock_code"] != stock_code])
    return {"ok": True}

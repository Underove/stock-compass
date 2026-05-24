"""관심종목 CRUD."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import get_current_user

router = APIRouter()

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _file(username: str) -> Path:
    return _DATA_DIR / f"watchlist_{username}.json"


def _load(username: str) -> list[dict]:
    f = _file(username)
    if not f.exists():
        return []
    with open(f, encoding="utf-8") as fp:
        return json.load(fp)


def _save(items: list[dict], username: str) -> None:
    with open(_file(username), "w", encoding="utf-8") as fp:
        json.dump(items, fp, ensure_ascii=False, indent=2)


class WatchlistItem(BaseModel):
    stock_code: str
    corp_name: str


@router.get("/watchlist")
def list_watchlist(username: str = Depends(get_current_user)):
    return {"items": _load(username)}


@router.post("/watchlist")
def add_watchlist(item: WatchlistItem, username: str = Depends(get_current_user)):
    items = _load(username)
    if not any(i["stock_code"] == item.stock_code for i in items):
        items.append(item.model_dump())
        _save(items, username)
    return {"ok": True}


@router.delete("/watchlist/{stock_code}")
def remove_watchlist(stock_code: str, username: str = Depends(get_current_user)):
    _save([i for i in _load(username) if i["stock_code"] != stock_code], username)
    return {"ok": True}

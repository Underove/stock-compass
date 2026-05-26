from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.db.trade_db import delete_trade, get_realized_summary, get_snapshots, get_trades, update_memo, update_trade

router = APIRouter()


class TradeOut(BaseModel):
    id: int
    stock_code: str
    corp_name: str
    trade_type: str
    quantity: int
    price: int
    buy_price: int | None
    memo: str | None
    created_at: str


class TradesResponse(BaseModel):
    trades: list[TradeOut]
    total: int


class MemoRequest(BaseModel):
    memo: str = Field(..., max_length=500)


class TradeSummaryItem(BaseModel):
    trade_id: int
    date: str
    corp_name: str
    stock_code: str
    quantity: int
    sell_price: int
    buy_price: int
    realized_pnl: int


class SnapshotOut(BaseModel):
    snapshot_date: str
    total_value: int
    total_invested: int


@router.get("/trades", response_model=TradesResponse)
def list_trades(
    limit: int = 50,
    offset: int = 0,
    stock_code: str | None = None,
    username: str = Depends(get_current_user),
) -> TradesResponse:
    trades, total = get_trades(username, limit=limit, offset=offset, stock_code=stock_code)
    return TradesResponse(trades=[TradeOut(**t) for t in trades], total=total)


@router.post("/trades/{trade_id}/memo")
def set_memo(
    trade_id: int,
    body: MemoRequest,
    username: str = Depends(get_current_user),
) -> dict:
    ok = update_memo(username, trade_id, body.memo)
    if not ok:
        raise HTTPException(404, "거래 내역을 찾을 수 없습니다")
    return {"ok": True}


@router.get("/trades/summary")
def trades_summary(username: str = Depends(get_current_user)) -> dict:
    rows = get_realized_summary(username)
    items = [
        TradeSummaryItem(
            trade_id=r["id"],
            date=r["date"],
            corp_name=r["corp_name"],
            stock_code=r["stock_code"],
            quantity=r["quantity"],
            sell_price=r["price"],
            buy_price=r["buy_price"],
            realized_pnl=r["realized_pnl"],
        )
        for r in rows
    ]
    return {"items": [i.model_dump() for i in items]}


class TradeUpdateRequest(BaseModel):
    trade_type: str = Field(..., pattern="^(buy|sell|edit)$")
    quantity: int = Field(..., ge=1)
    price: int = Field(..., ge=0)
    buy_price: int | None = None


@router.put("/trades/{trade_id}")
def edit_trade(
    trade_id: int,
    body: TradeUpdateRequest,
    username: str = Depends(get_current_user),
) -> dict:
    ok = update_trade(username, trade_id, body.trade_type, body.quantity, body.price, body.buy_price)
    if not ok:
        raise HTTPException(404, "거래 내역을 찾을 수 없습니다")
    return {"ok": True}


@router.delete("/trades/{trade_id}")
def remove_trade(
    trade_id: int,
    username: str = Depends(get_current_user),
) -> dict:
    ok = delete_trade(username, trade_id)
    if not ok:
        raise HTTPException(404, "거래 내역을 찾을 수 없습니다")
    return {"ok": True}


@router.get("/portfolio/snapshots")
def portfolio_snapshots(
    days: int = 90,
    username: str = Depends(get_current_user),
) -> dict:
    snaps = get_snapshots(username, days=days)
    return {"snapshots": [SnapshotOut(**s).model_dump() for s in snaps]}

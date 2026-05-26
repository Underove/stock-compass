"use client";
import { useEffect, useRef, useState } from "react";
import type { Trade } from "../lib/types";
import { deleteTrade, editTrade, updateTradeMemo } from "../lib/api";

interface Props {
  trade: Trade;
  currentPrice?: number;
  onClose: () => void;
  onMemoSaved?: (tradeId: number, memo: string) => void;
  onDeleted?: (tradeId: number) => void;
  onEdited?: (updated: Trade) => void;
}

const BADGE_STYLE: Record<Trade["trade_type"], { label: string; bg: string; color: string }> = {
  buy: { label: "매수", bg: "var(--success)", color: "#fff" },
  sell: { label: "매도", bg: "var(--danger)", color: "#fff" },
  edit: { label: "수정", bg: "var(--primary)", color: "#fff" },
};

export default function TradeDetailModal({ trade, currentPrice, onClose, onMemoSaved, onDeleted, onEdited }: Props) {
  const [memo, setMemo] = useState(trade.memo ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // 수정 모드
  const [editMode, setEditMode] = useState(false);
  const [editType, setEditType] = useState<Trade["trade_type"]>(trade.trade_type);
  const [editQty, setEditQty] = useState(String(trade.quantity));
  const [editPrice, setEditPrice] = useState(String(trade.price));
  const [editBuyPrice, setEditBuyPrice] = useState(String(trade.buy_price ?? ""));
  const [editSaving, setEditSaving] = useState(false);

  // 삭제 확인
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const badge = BADGE_STYLE[trade.trade_type];
  const total = trade.price * trade.quantity;
  const date = trade.created_at.replace("T", " ").slice(0, 16);

  let evalPnl: number | null = null;
  let evalPnlPct: number | null = null;
  if (trade.trade_type !== "sell" && currentPrice != null && trade.price > 0) {
    evalPnl = (currentPrice - trade.price) * trade.quantity;
    evalPnlPct = ((currentPrice - trade.price) / trade.price) * 100;
  }
  // sell일 때는 실현 손익 표시
  let realizedPnl: number | null = null;
  if (trade.trade_type === "sell" && trade.buy_price != null) {
    realizedPnl = (trade.price - trade.buy_price) * trade.quantity;
  }

  async function handleSaveMemo() {
    setSaving(true);
    try {
      await updateTradeMemo(trade.id, memo);
      setSaved(true);
      onMemoSaved?.(trade.id, memo);
      setTimeout(() => setSaved(false), 1500);
    } catch { /* ignore */ }
    finally { setSaving(false); }
  }

  async function handleEdit() {
    const qty = parseInt(editQty, 10);
    const price = parseInt(editPrice.replace(/,/g, ""), 10);
    const buyPrice = editBuyPrice ? parseInt(editBuyPrice.replace(/,/g, ""), 10) : null;
    if (!qty || !price) return;
    setEditSaving(true);
    try {
      await editTrade(trade.id, editType, qty, price, buyPrice);
      const updated: Trade = { ...trade, trade_type: editType, quantity: qty, price, buy_price: buyPrice };
      onEdited?.(updated);
      setEditMode(false);
    } catch { /* ignore */ }
    finally { setEditSaving(false); }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      await deleteTrade(trade.id);
      onDeleted?.(trade.id);
      onClose();
    } catch { /* ignore */ }
    finally { setDeleting(false); }
  }

  const inputStyle: React.CSSProperties = {
    background: "var(--surface3)", border: "1px solid var(--border)",
    borderRadius: 8, padding: "8px 10px", color: "var(--label1)",
    fontSize: 14, width: "100%", boxSizing: "border-box",
  };

  return (
    <div
      ref={overlayRef}
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
      style={{
        position: "fixed", inset: 0, zIndex: 200,
        background: "rgba(0,0,0,0.55)", display: "flex",
        alignItems: "center", justifyContent: "center", padding: "24px",
      }}
    >
      <div style={{
        background: "var(--surface)", borderRadius: 16,
        width: "100%", maxWidth: 400, padding: "24px",
        boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
        border: "0.5px solid var(--sep)",
        display: "flex", flexDirection: "column", gap: 16,
        maxHeight: "90vh", overflowY: "auto",
      }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: "var(--label1)", marginBottom: 4 }}>
              {trade.corp_name}
              <span style={{ fontSize: 13, color: "var(--label3)", marginLeft: 7, fontWeight: 500 }}>
                {trade.stock_code}
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{
                fontSize: 11, fontWeight: 700, padding: "2px 8px",
                borderRadius: 7, background: badge.bg, color: badge.color,
              }}>{badge.label}</span>
              <span style={{ fontSize: 12, color: "var(--label3)" }}>{date}</span>
            </div>
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
            <button
              onClick={() => { setEditMode(!editMode); setConfirmDelete(false); }}
              style={{
                background: editMode ? "var(--primary)" : "rgba(118,118,128,0.12)",
                border: "none", cursor: "pointer",
                color: editMode ? "#fff" : "var(--label2)",
                fontSize: 12, fontWeight: 600, padding: "6px 12px",
                borderRadius: 9,
              }}
            >
              {editMode ? "취소" : "수정"}
            </button>
            <button
              onClick={onClose}
              style={{
                background: "rgba(118,118,128,0.12)", border: "none", cursor: "pointer",
                color: "var(--label3)", fontSize: 16, padding: "0",
                width: 30, height: 30, borderRadius: "50%",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}
            >✕</button>
          </div>
        </div>

        {/* Edit Mode Form */}
        {editMode ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {/* Trade type toggle */}
            <div>
              <div style={{ fontSize: 11, color: "var(--label3)", marginBottom: 6 }}>거래 유형</div>
              <div style={{ display: "flex", gap: 6 }}>
                {(["buy", "sell", "edit"] as Trade["trade_type"][]).map((t) => (
                  <button
                    key={t}
                    onClick={() => setEditType(t)}
                    style={{
                      flex: 1, padding: "7px 0", borderRadius: 8, border: "none", cursor: "pointer",
                      fontSize: 12, fontWeight: 700,
                      background: editType === t ? BADGE_STYLE[t].bg : "var(--surface3)",
                      color: editType === t ? "#fff" : "var(--label2)",
                    }}
                  >
                    {BADGE_STYLE[t].label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "var(--label3)", marginBottom: 4 }}>수량 (주)</div>
              <input
                type="number" value={editQty} onChange={(e) => setEditQty(e.target.value)}
                style={inputStyle} min={1}
              />
            </div>
            <div>
              <div style={{ fontSize: 11, color: "var(--label3)", marginBottom: 4 }}>
                {editType === "sell" ? "매도 단가" : "매수 단가"} (원)
              </div>
              <input
                type="number" value={editPrice} onChange={(e) => setEditPrice(e.target.value)}
                style={inputStyle} min={0}
              />
            </div>
            {editType === "sell" && (
              <div>
                <div style={{ fontSize: 11, color: "var(--label3)", marginBottom: 4 }}>평균 매수단가 (원, 손익 계산용)</div>
                <input
                  type="number" value={editBuyPrice} onChange={(e) => setEditBuyPrice(e.target.value)}
                  style={inputStyle} min={0}
                />
              </div>
            )}
            <button
              onClick={handleEdit}
              disabled={editSaving}
              style={{
                padding: "10px", background: "var(--primary)", color: "#fff",
                border: "none", borderRadius: 10, fontSize: 14, fontWeight: 600,
                cursor: "pointer", opacity: editSaving ? 0.7 : 1,
              }}
            >
              {editSaving ? "저장 중…" : "수정 저장"}
            </button>
          </div>
        ) : (
          <>
            {/* Stats */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {[
                { label: "수량", value: `${trade.quantity.toLocaleString()}주` },
                { label: trade.trade_type === "sell" ? "매도 단가" : "매수 단가", value: `${trade.price.toLocaleString()}원` },
                { label: "총액", value: `${total.toLocaleString()}원` },
                ...(currentPrice != null
                  ? [{ label: "현재가", value: `${currentPrice.toLocaleString()}원` }]
                  : []),
              ].map(({ label, value }) => (
                <div key={label} style={{ background: "rgba(118,118,128,0.08)", borderRadius: 12, padding: "12px 14px" }}>
                  <div style={{ fontSize: 11, color: "var(--label3)", marginBottom: 3 }}>{label}</div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: "var(--label1)", letterSpacing: "-0.03em" }}>{value}</div>
                </div>
              ))}
            </div>

            {/* Realized P&L (sell) */}
            {realizedPnl != null && (
              <div style={{
                background: realizedPnl >= 0 ? "rgba(255,59,48,0.12)" : "rgba(30,144,255,0.12)",
                borderRadius: 10, padding: "10px 14px",
              }}>
                <div style={{ fontSize: 11, color: "var(--label3)", marginBottom: 2 }}>실현 손익</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: realizedPnl >= 0 ? "var(--danger)" : "#1e90ff" }}>
                  {realizedPnl >= 0 ? "+" : ""}{realizedPnl.toLocaleString()}원
                  {trade.buy_price != null && trade.buy_price > 0 && (
                    <span style={{ fontSize: 12, marginLeft: 6 }}>
                      ({(((trade.price - trade.buy_price) / trade.buy_price) * 100).toFixed(2)}%)
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Eval P&L (buy/edit, portfolio 보유 중) */}
            {evalPnl != null && evalPnlPct != null && (
              <div style={{
                background: evalPnl >= 0 ? "rgba(255,59,48,0.12)" : "rgba(30,144,255,0.12)",
                borderRadius: 10, padding: "10px 14px",
              }}>
                <div style={{ fontSize: 11, color: "var(--label3)", marginBottom: 2 }}>평가손익 (현재가 기준)</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: evalPnl >= 0 ? "var(--danger)" : "#1e90ff" }}>
                  {evalPnl >= 0 ? "+" : ""}{evalPnl.toLocaleString()}원
                  <span style={{ fontSize: 12, marginLeft: 6 }}>
                    ({evalPnlPct >= 0 ? "+" : ""}{evalPnlPct.toFixed(2)}%)
                  </span>
                </div>
              </div>
            )}

            {/* Memo */}
            <div>
              <div style={{ fontSize: 12, color: "var(--label3)", marginBottom: 6 }}>메모</div>
              <textarea
                value={memo}
                onChange={(e) => setMemo(e.target.value)}
                placeholder="거래 메모를 입력하세요"
                rows={3}
                style={{
                  width: "100%", resize: "none", boxSizing: "border-box",
                  background: "var(--surface3)", border: "1px solid var(--border)",
                  borderRadius: 10, padding: "10px 12px", color: "var(--label1)",
                  fontSize: 14, lineHeight: 1.5,
                }}
              />
              <button
                onClick={handleSaveMemo}
                disabled={saving}
                style={{
                  marginTop: 8, width: "100%", padding: "10px",
                  background: saved ? "var(--success)" : "var(--primary)",
                  color: "#fff", border: "none", borderRadius: 10,
                  fontSize: 14, fontWeight: 600, cursor: "pointer",
                  opacity: saving ? 0.7 : 1,
                }}
              >
                {saved ? "저장됨" : saving ? "저장 중…" : "메모 저장"}
              </button>
            </div>
          </>
        )}

        {/* Delete */}
        {!editMode && (
          <div style={{ borderTop: "0.5px solid var(--sep)", paddingTop: 14 }}>
            {!confirmDelete ? (
              <button
                onClick={() => setConfirmDelete(true)}
                style={{
                  width: "100%", padding: "10px", background: "rgba(255,59,48,0.07)",
                  border: "none", color: "var(--danger)",
                  borderRadius: 12, fontSize: 13, fontWeight: 600, cursor: "pointer",
                }}
              >
                이 거래 삭제
              </button>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--label1)", textAlign: "center" }}>
                  이 거래를 삭제할까요?
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    onClick={() => setConfirmDelete(false)}
                    style={{
                      flex: 1, padding: "10px", background: "rgba(118,118,128,0.1)",
                      border: "none", color: "var(--label2)",
                      borderRadius: 12, fontSize: 13, fontWeight: 600, cursor: "pointer",
                    }}
                  >
                    취소
                  </button>
                  <button
                    onClick={handleDelete}
                    disabled={deleting}
                    style={{
                      flex: 1, padding: "10px", background: "var(--danger)",
                      border: "none", color: "#fff",
                      borderRadius: 12, fontSize: 13, fontWeight: 700, cursor: "pointer",
                      opacity: deleting ? 0.7 : 1,
                    }}
                  >
                    {deleting ? "삭제 중…" : "삭제"}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

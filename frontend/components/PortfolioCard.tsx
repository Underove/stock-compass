"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  addPortfolioItem,
  addWatchlistItem,
  fetchPortfolioAlerts,
  fetchStockPrice,
  listPortfolio,
  listWatchlist,
  removePortfolioItem,
  removeWatchlistItem,
  searchStock,
  updatePortfolioItem,
} from "../lib/api";
import { useRealtimePrice } from "../hooks/useRealtimePrice";
import type { RealtimePrice } from "../hooks/useRealtimePrice";
import type { PortfolioItem, SearchResult, StockPrice, WatchlistItem } from "../lib/types";
import { StockDetailModal } from "./StockDetailModal";

type Tab = "stocks" | "watchlist" | "allocation";

function StockLogo({ code, name, isEditing }: { code: string; name: string; isEditing: boolean }) {
  return (
    <div style={{
      width: 40, height: 40, borderRadius: 12,
      background: isEditing ? "rgba(0,122,255,0.1)" : "var(--surface2)",
      display: "flex", alignItems: "center", justifyContent: "center",
      flexShrink: 0, transition: "all 0.15s",
      fontSize: 16, fontWeight: 800,
      color: isEditing ? "var(--primary)" : "var(--label2)",
    }}>
      {name.slice(0, 1)}
    </div>
  );
}

function fmt(n: number) { return n.toLocaleString("ko-KR"); }
function pctColor(pct: number) {
  if (pct > 0) return "var(--red)";
  if (pct < 0) return "var(--primary)";
  return "var(--label2)";
}
function pctSign(pct: number) {
  return pct > 0 ? `+${pct.toFixed(2)}%` : `${pct.toFixed(2)}%`;
}

// ─── 천단위 콤마 입력 컴포넌트 ────────────────────────────────────────────────

function CommaInput({ value, onChange, placeholder, autoFocus, style }: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
  style?: React.CSSProperties;
}) {
  const num = value !== "" ? parseInt(value, 10) : NaN;
  const display = !isNaN(num) ? num.toLocaleString("ko-KR") : "";
  return (
    <input
      type="text"
      inputMode="numeric"
      value={display}
      onChange={e => onChange(e.target.value.replace(/,/g, "").replace(/[^0-9]/g, ""))}
      placeholder={placeholder}
      autoFocus={autoFocus}
      style={style}
    />
  );
}

// ─── 탭 바 ───────────────────────────────────────────────────────────────────

function TabBar({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  const tabs: { key: Tab; label: string }[] = [
    { key: "stocks", label: "내 주식" },
    { key: "watchlist", label: "관심종목" },
    { key: "allocation", label: "배분" },
  ];
  return (
    <div style={{ display: "flex", borderBottom: "0.5px solid var(--sep)", flexShrink: 0 }}>
      {tabs.map(t => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          style={{
            flex: 1, padding: "10px 4px 11px",
            fontSize: 13, fontWeight: active === t.key ? 700 : 500,
            color: active === t.key ? "var(--primary)" : "var(--label3)",
            borderBottom: `2.5px solid ${active === t.key ? "var(--primary)" : "transparent"}`,
            transition: "all 0.15s", marginBottom: -1,
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

// ─── 포트폴리오 요약 카드 ──────────────────────────────────────────────────────

function SummaryCard({ items, prices }: { items: PortfolioItem[]; prices: Record<string, StockPrice> }) {
  const totalInvested = items.reduce((s, i) => s + i.buy_price * i.quantity, 0);
  const totalCurrent = items.reduce((s, i) => {
    const p = prices[i.stock_code];
    return s + (p ? p.current_price * i.quantity : i.buy_price * i.quantity);
  }, 0);
  const totalPnl = totalCurrent - totalInvested;
  const totalPnlPct = totalInvested > 0 ? (totalPnl / totalInvested) * 100 : 0;
  const todayPnl = items.reduce((s, i) => {
    const p = prices[i.stock_code];
    if (!p || !isFinite(p.open) || p.open === 0) return s;
    return s + (p.current_price - p.open) * i.quantity;
  }, 0);
  const isProfit = totalPnl >= 0;
  const isTodayProfit = todayPnl >= 0;

  function fmtShort(n: number) {
    const abs = Math.abs(n);
    if (abs >= 1e8) return `${(n / 1e8).toFixed(1)}억`;
    return `${Math.round(n / 1e4).toLocaleString("ko-KR")}만`;
  }

  const cellStyle: React.CSSProperties = { flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3 };
  const labelStyle: React.CSSProperties = { fontSize: 10, color: "var(--label3)", fontWeight: 500 };

  return (
    <div style={{ margin: "12px 16px 4px", background: "var(--surface)", borderRadius: 16, boxShadow: "var(--shadow)" }}>
      <div style={{ display: "flex", padding: "12px 8px" }}>
        <div style={cellStyle}>
          <span style={labelStyle}>총 평가</span>
          <span style={{ fontSize: 14, fontWeight: 800, color: "var(--label)", letterSpacing: "-0.03em" }}>
            {fmtShort(totalCurrent)}
          </span>
        </div>
        <div style={{ width: "0.5px", background: "var(--sep)", alignSelf: "stretch" }} />
        <div style={cellStyle}>
          <span style={labelStyle}>수익률</span>
          <span style={{ fontSize: 14, fontWeight: 800, color: isProfit ? "var(--red)" : "var(--primary)", letterSpacing: "-0.03em" }}>
            {totalPnlPct > 0 ? "+" : ""}{totalPnlPct.toFixed(2)}%
          </span>
        </div>
        <div style={{ width: "0.5px", background: "var(--sep)", alignSelf: "stretch" }} />
        <div style={cellStyle}>
          <span style={labelStyle}>오늘 손익</span>
          <span style={{ fontSize: 14, fontWeight: 800, color: isTodayProfit ? "var(--red)" : "var(--primary)", letterSpacing: "-0.03em" }}>
            {todayPnl > 0 ? "+" : ""}{fmtShort(todayPnl)}
          </span>
        </div>
      </div>
    </div>
  );
}

// ─── 종목 추가 패널 ───────────────────────────────────────────────────────────

function AddStockPanel({ onAdd, onClose }: { onAdd: (item: PortfolioItem) => void; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [buyPrice, setBuyPrice] = useState("");
  const [quantity, setQuantity] = useState("");
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    const t = setTimeout(async () => {
      if (!query.trim()) { setResults([]); return; }
      setSearching(true);
      try { setResults((await searchStock(query)).slice(0, 6)); }
      catch { setResults([]); }
      finally { setSearching(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  function confirm() {
    if (!selected) return;
    const bp = parseInt(buyPrice, 10), qty = parseInt(quantity, 10);
    if (isNaN(bp) || isNaN(qty) || bp <= 0 || qty <= 0) return;
    onAdd({ stock_code: selected.stock_code, corp_name: selected.corp_name, buy_price: bp, quantity: qty });
    onClose();
  }

  return (
    <div style={{ background: "var(--surface)", borderRadius: 16, border: "0.5px solid var(--sep)", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 16px", borderBottom: "0.5px solid var(--sep)" }}>
        <span style={{ fontSize: 14, fontWeight: 700 }}>종목 추가</span>
        <button onClick={onClose} style={{ fontSize: 13, color: "var(--label2)" }}>취소</button>
      </div>
      <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
        {!selected ? (
          <>
            <input type="text" value={query} onChange={e => setQuery(e.target.value)} placeholder="종목명 입력 (예: 삼성전자)" autoFocus
              style={{ width: "100%", background: "var(--bg)", borderRadius: 10, padding: "10px 14px", fontSize: 14, border: "none", outline: "none" }} />
            {searching && <div style={{ fontSize: 13, color: "var(--label2)", textAlign: "center" }}>검색 중…</div>}
            {results.length > 0 && (
              <div style={{ background: "var(--bg)", borderRadius: 10, overflow: "hidden" }}>
                {results.map((r, i) => (
                  <div key={r.stock_code}>
                    {i > 0 && <div style={{ height: "0.5px", background: "var(--sep)", marginLeft: 12 }} />}
                    <button onClick={() => setSelected(r)} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", padding: "10px 14px", textAlign: "left" }}>
                      <span style={{ fontSize: 14, fontWeight: 600 }}>{r.corp_name}</span>
                      <span style={{ fontSize: 12, color: "var(--label2)", fontFamily: "monospace" }}>{r.stock_code}</span>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : (
          <>
            <div style={{ background: "rgba(0,122,255,0.08)", borderRadius: 10, padding: "9px 14px", display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: "var(--primary)" }}>{selected.corp_name}</span>
              <button onClick={() => setSelected(null)} style={{ fontSize: 13, color: "var(--label2)" }}>변경</button>
            </div>
            <CommaInput value={buyPrice} onChange={setBuyPrice} placeholder="매수 단가 (원)"
              style={{ width: "100%", background: "var(--bg)", borderRadius: 10, padding: "10px 14px", fontSize: 14, border: "none", outline: "none" }} />
            <CommaInput value={quantity} onChange={setQuantity} placeholder="보유 수량 (주)"
              style={{ width: "100%", background: "var(--bg)", borderRadius: 10, padding: "10px 14px", fontSize: 14, border: "none", outline: "none" }} />
            <button onClick={confirm} disabled={!buyPrice || !quantity}
              style={{ width: "100%", padding: "11px", background: !buyPrice || !quantity ? "var(--label3)" : "var(--primary)", color: "white", borderRadius: 10, fontSize: 14, fontWeight: 700 }}>
              등록
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ─── 매매 패널 ────────────────────────────────────────────────────────────────

type TradeMode = "buy" | "sell" | "edit";

function TradePanel({ item, onSave, onDelete, onCancel }: {
  item: PortfolioItem;
  onSave: (quantity: number, buyPrice: number) => Promise<void>;
  onDelete: () => Promise<void>;
  onCancel: () => void;
}) {
  const [mode, setMode] = useState<TradeMode>("buy");
  const [tradeQty, setTradeQty] = useState("");
  const [tradePrice, setTradePrice] = useState("");
  const [editQty, setEditQty] = useState(item.quantity.toString());
  const [editPrice, setEditPrice] = useState(item.buy_price.toString());
  const [saving, setSaving] = useState(false);

  const buyQty = parseInt(tradeQty, 10);
  const buyPrice = parseInt(tradePrice, 10);
  const newAvg = !isNaN(buyQty) && buyQty > 0 && !isNaN(buyPrice) && buyPrice > 0
    ? Math.round((item.quantity * item.buy_price + buyQty * buyPrice) / (item.quantity + buyQty))
    : null;
  const newBuyTotal = newAvg !== null ? (item.quantity + buyQty) * newAvg : null;
  const avgDiff = newAvg !== null ? newAvg - item.buy_price : null;

  const sellQty = parseInt(tradeQty, 10);
  const remainQty = !isNaN(sellQty) && sellQty > 0 ? item.quantity - sellQty : null;
  const sellPct = remainQty !== null && remainQty >= 0 ? Math.min(100, (sellQty / item.quantity) * 100) : 0;

  async function handleBuy() {
    if (!newAvg || isNaN(buyQty) || buyQty <= 0) return;
    setSaving(true);
    try { await onSave(item.quantity + buyQty, newAvg); } finally { setSaving(false); }
  }

  async function handleSell() {
    if (remainQty === null || remainQty < 0) return;
    setSaving(true);
    try { await onSave(remainQty, item.buy_price); } finally { setSaving(false); }
  }

  async function handleEdit() {
    const q = parseInt(editQty, 10), p = parseInt(editPrice, 10);
    if (isNaN(q) || isNaN(p) || p <= 0) return;
    setSaving(true);
    try { await onSave(q, p); } finally { setSaving(false); }
  }

  async function handleDelete() {
    setSaving(true);
    try { await onDelete(); } finally { setSaving(false); }
  }

  const modeLabels: { key: TradeMode; label: string }[] = [
    { key: "buy", label: "추가 매수" },
    { key: "sell", label: "일부 매도" },
    { key: "edit", label: "직접 수정" },
  ];

  return (
    <div style={{ margin: "0 16px 10px", background: "var(--surface)", borderRadius: 16, overflow: "hidden", boxShadow: "var(--shadow)" }}>
      {/* 세그먼트 컨트롤 */}
      <div style={{ padding: "10px 10px 0" }}>
        <div style={{ display: "flex", background: "var(--bg)", borderRadius: 11, padding: 3, gap: 2 }}>
          {modeLabels.map(m => {
            const isActive = mode === m.key;
            const activeColor = m.key === "sell" ? "var(--red)" : "var(--primary)";
            return (
              <button
                key={m.key}
                onClick={() => { setMode(m.key); setTradeQty(""); setTradePrice(""); }}
                style={{
                  flex: 1, padding: "7px 4px",
                  fontSize: 12, fontWeight: 700,
                  color: isActive ? activeColor : "var(--label3)",
                  background: isActive ? "var(--surface)" : "transparent",
                  borderRadius: 9,
                  boxShadow: isActive ? "0 1px 4px rgba(0,0,0,0.10)" : "none",
                  transition: "all 0.18s",
                }}
              >
                {m.label}
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ padding: "10px 14px 12px" }}>
        {/* ── 추가 매수 ── */}
        {mode === "buy" && (
          <>
            <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 3 }}>매수 수량 (주)</div>
                <CommaInput value={tradeQty} onChange={setTradeQty} placeholder="0"
                  autoFocus
                  style={{ width: "100%", background: "var(--bg)", borderRadius: 8, padding: "8px 10px", fontSize: 14, border: "none", outline: "none" }} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 3 }}>매수 단가 (원)</div>
                <CommaInput value={tradePrice} onChange={setTradePrice} placeholder="0"
                  style={{ width: "100%", background: "var(--bg)", borderRadius: 8, padding: "8px 10px", fontSize: 14, border: "none", outline: "none" }} />
              </div>
            </div>
            {newAvg !== null && (
              <div style={{ background: "rgba(0,122,255,0.06)", borderRadius: 12, padding: "12px 14px", marginBottom: 10, border: "0.5px solid rgba(0,122,255,0.12)" }}>
                <div style={{ fontSize: 10, color: "var(--primary)", fontWeight: 700, marginBottom: 8, letterSpacing: "0.04em" }}>매수 후 예상</div>
                <div style={{ display: "flex", alignItems: "flex-end", gap: 6, marginBottom: 10 }}>
                  <div>
                    <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 2 }}>기존 단가</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "var(--label2)" }}>{fmt(item.buy_price)}원</div>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--label3)", paddingBottom: 2 }}>→</div>
                  <div>
                    <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 2 }}>새 평균단가</div>
                    <div style={{ fontSize: 18, fontWeight: 800, color: "var(--primary)", letterSpacing: "-0.04em" }}>{fmt(newAvg)}원</div>
                  </div>
                  {avgDiff !== null && (
                    <div style={{ marginLeft: "auto", textAlign: "right", paddingBottom: 2 }}>
                      <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 2 }}>단가 변동</div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: avgDiff > 0 ? "var(--red)" : avgDiff < 0 ? "var(--primary)" : "var(--label3)" }}>
                        {avgDiff > 0 ? "+" : ""}{fmt(avgDiff)}원
                      </div>
                    </div>
                  )}
                </div>
                <div style={{ display: "flex", borderTop: "0.5px solid rgba(0,122,255,0.12)", paddingTop: 8 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 1 }}>총 수량</div>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>{fmt(item.quantity + buyQty)}주</div>
                  </div>
                  <div style={{ flex: 1, textAlign: "center" }}>
                    <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 1 }}>추가 투자금</div>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>{fmt(buyQty * buyPrice)}원</div>
                  </div>
                  <div style={{ flex: 1, textAlign: "right" }}>
                    <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 1 }}>총 투자금</div>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>{fmt(newBuyTotal ?? 0)}원</div>
                  </div>
                </div>
              </div>
            )}
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={handleBuy} disabled={saving || !newAvg}
                style={{ flex: 1, padding: "10px", background: !newAvg || saving ? "var(--label3)" : "var(--primary)", color: "white", borderRadius: 10, fontSize: 13, fontWeight: 700 }}>
                {saving ? "저장 중…" : "매수 반영"}
              </button>
              <button onClick={onCancel}
                style={{ padding: "10px 14px", background: "var(--bg)", color: "var(--label2)", borderRadius: 10, fontSize: 13 }}>
                취소
              </button>
            </div>
          </>
        )}

        {/* ── 일부 매도 ── */}
        {mode === "sell" && (
          <>
            <div style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                <div style={{ fontSize: 10, color: "var(--label3)" }}>매도 수량 (주)</div>
                <div style={{ fontSize: 10, color: "var(--label3)" }}>보유 {fmt(item.quantity)}주</div>
              </div>
              <CommaInput value={tradeQty} onChange={setTradeQty} placeholder="0"
                autoFocus
                style={{ width: "100%", background: "var(--bg)", borderRadius: 8, padding: "8px 10px", fontSize: 14, border: "none", outline: "none" }} />
            </div>
            {remainQty !== null && remainQty >= 0 && (
              <div style={{
                background: remainQty === 0 ? "rgba(255,59,48,0.06)" : "rgba(255,59,48,0.04)",
                borderRadius: 12, padding: "12px 14px", marginBottom: 10,
                border: `0.5px solid ${remainQty === 0 ? "rgba(255,59,48,0.2)" : "rgba(255,59,48,0.1)"}`,
              }}>
                <div style={{ fontSize: 10, color: "var(--red)", fontWeight: 700, marginBottom: 8, letterSpacing: "0.04em" }}>
                  {remainQty === 0 ? "전량 매도" : "매도 후 예상"}
                </div>
                {remainQty > 0 ? (
                  <>
                    <div style={{ marginBottom: 10 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ fontSize: 11, color: "var(--label3)" }}>매도 비중</span>
                        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--red)" }}>{sellPct.toFixed(0)}%</span>
                      </div>
                      <div style={{ height: 5, background: "var(--bg)", borderRadius: 3, overflow: "hidden" }}>
                        <div style={{ height: "100%", width: `${sellPct}%`, background: "var(--red)", borderRadius: 3, transition: "width 0.2s" }} />
                      </div>
                    </div>
                    <div style={{ display: "flex", borderTop: "0.5px solid rgba(255,59,48,0.1)", paddingTop: 8 }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 1 }}>매도 후 잔여</div>
                        <div style={{ fontSize: 16, fontWeight: 800 }}>{fmt(remainQty)}주</div>
                      </div>
                      <div style={{ flex: 1, textAlign: "right" }}>
                        <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 1 }}>잔여 원금</div>
                        <div style={{ fontSize: 13, fontWeight: 700 }}>{fmt(remainQty * item.buy_price)}원</div>
                      </div>
                    </div>
                  </>
                ) : (
                  <div style={{ textAlign: "center", padding: "6px 0 2px" }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "var(--red)" }}>모든 보유 주식 매도</div>
                    <div style={{ fontSize: 11, color: "var(--label3)", marginTop: 2 }}>포트폴리오에서 삭제됩니다</div>
                  </div>
                )}
              </div>
            )}
            {remainQty !== null && remainQty < 0 && (
              <div style={{ fontSize: 12, color: "var(--red)", marginBottom: 8 }}>보유 수량을 초과했습니다.</div>
            )}
            <div style={{ display: "flex", gap: 6 }}>
              <button
                onClick={handleSell}
                disabled={saving || remainQty === null || remainQty < 0}
                style={{
                  flex: 1, padding: "10px",
                  background: saving || remainQty === null || remainQty < 0 ? "var(--label3)" : "var(--red)",
                  color: "white", borderRadius: 10, fontSize: 13, fontWeight: 700,
                }}
              >
                {saving ? "저장 중…" : remainQty === 0 ? "전량 매도" : "매도 반영"}
              </button>
              <button onClick={onCancel}
                style={{ padding: "10px 14px", background: "var(--bg)", color: "var(--label2)", borderRadius: 10, fontSize: 13 }}>
                취소
              </button>
            </div>
          </>
        )}

        {/* ── 직접 수정 ── */}
        {mode === "edit" && (
          <>
            <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 3 }}>수량 (주)</div>
                <CommaInput value={editQty} onChange={setEditQty}
                  autoFocus
                  style={{ width: "100%", background: "var(--bg)", borderRadius: 8, padding: "8px 10px", fontSize: 14, border: "none", outline: "none" }} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 3 }}>평균단가 (원)</div>
                <CommaInput value={editPrice} onChange={setEditPrice}
                  style={{ width: "100%", background: "var(--bg)", borderRadius: 8, padding: "8px 10px", fontSize: 14, border: "none", outline: "none" }} />
              </div>
            </div>
            <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
              <button onClick={handleEdit} disabled={saving || !editQty || !editPrice}
                style={{ flex: 1, padding: "10px", background: saving ? "var(--label3)" : "var(--primary)", color: "white", borderRadius: 10, fontSize: 13, fontWeight: 700 }}>
                {saving ? "저장 중…" : "저장"}
              </button>
              <button onClick={onCancel}
                style={{ padding: "10px 14px", background: "var(--bg)", color: "var(--label2)", borderRadius: 10, fontSize: 13 }}>
                취소
              </button>
            </div>
            <button onClick={handleDelete} disabled={saving}
              style={{ width: "100%", padding: "9px", background: "rgba(255,59,48,0.08)", color: "var(--red)", borderRadius: 10, fontSize: 12, fontWeight: 600 }}>
              종목 삭제
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ─── 종목 행 ──────────────────────────────────────────────────────────────────

function StockRow({ item, onClick, onEdit, onPriceLoaded, alertCount, realtimePrice, isEditing }: {
  item: PortfolioItem; onClick: () => void; onEdit: () => void;
  onPriceLoaded: (code: string, price: StockPrice) => void;
  alertCount: number; realtimePrice?: RealtimePrice; isEditing: boolean;
}) {
  const [price, setPrice] = useState<StockPrice | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStockPrice(item.stock_code)
      .then(p => { setPrice(p); onPriceLoaded(item.stock_code, p); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [item.stock_code, onPriceLoaded]);

  const currentPrice = realtimePrice?.current_price ?? price?.current_price ?? null;
  const evalPnlPct = currentPrice && item.buy_price ? ((currentPrice - item.buy_price) / item.buy_price) * 100 : null;
  const evalPnl = currentPrice ? (currentPrice - item.buy_price) * item.quantity : null;
  const isLive = !!realtimePrice;
  const hitTarget = item.target_price && currentPrice && currentPrice >= item.target_price;
  const hitStop = item.stop_loss && currentPrice && currentPrice <= item.stop_loss;

  const accentColor = evalPnlPct === null ? "var(--sep)"
    : evalPnlPct > 0 ? "var(--red)"
    : evalPnlPct < 0 ? "var(--primary)"
    : "var(--label3)";

  return (
    <div style={{ position: "relative", background: isEditing ? "rgba(0,122,255,0.025)" : "transparent", transition: "background 0.15s" }}>

      <div
        style={{ display: "flex", alignItems: "center", padding: "12px 16px", gap: 12, cursor: "pointer" }}
        onClick={onClick}
      >
        {/* 로고 */}
        <StockLogo code={item.stock_code} name={item.corp_name} isEditing={isEditing} />

        {/* 이름 + 보유 정보 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 2 }}>
            <span style={{ fontSize: 14, fontWeight: 700, letterSpacing: "-0.02em" }}>{item.corp_name}</span>
            {isLive && <span style={{ fontSize: 8, fontWeight: 700, color: "var(--green)", background: "rgba(52,199,89,0.12)", borderRadius: 4, padding: "1px 4px" }}>LIVE</span>}
            {hitTarget && <span style={{ fontSize: 8, fontWeight: 700, color: "var(--red)", background: "rgba(255,59,48,0.1)", borderRadius: 4, padding: "1px 5px" }}>목표</span>}
            {hitStop && <span style={{ fontSize: 8, fontWeight: 700, color: "var(--primary)", background: "rgba(0,122,255,0.1)", borderRadius: 4, padding: "1px 5px" }}>손절</span>}
          </div>
          <div style={{ fontSize: 11, color: "var(--label3)" }}>
            {fmt(item.quantity)}주 · 단가 {fmt(item.buy_price)}원
          </div>
          {evalPnl !== null && (
            <div style={{ fontSize: 11, fontWeight: 600, color: accentColor, marginTop: 1 }}>
              {evalPnl > 0 ? "+" : ""}{fmt(evalPnl)}원
            </div>
          )}
        </div>

        {/* 현재가 + 등락 */}
        <div style={{ textAlign: "right", flexShrink: 0, minWidth: 68 }}>
          {loading && !realtimePrice ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end" }}>
              <div style={{ width: 54, height: 14, background: "var(--surface2)", borderRadius: 4, animation: "pulse 1.4s ease-in-out infinite" }} />
              <div style={{ width: 38, height: 11, background: "var(--surface2)", borderRadius: 4, animation: "pulse 1.4s ease-in-out infinite" }} />
            </div>
          ) : currentPrice !== null ? (
            <>
              <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: "-0.03em" }}>{fmt(currentPrice)}</div>
              <div style={{ fontSize: 12, fontWeight: 700, color: evalPnlPct !== null ? pctColor(evalPnlPct) : "var(--label3)" }}>
                {evalPnlPct !== null ? pctSign(evalPnlPct) : "—"}
              </div>
            </>
          ) : (
            <div style={{ fontSize: 11, color: "var(--label3)" }}>조회 실패</div>
          )}
        </div>

        {/* 거래 버튼 */}
        <div style={{ flexShrink: 0 }} onClick={e => e.stopPropagation()}>
          <button
            onClick={onEdit}
            style={{
              padding: "6px 12px", borderRadius: 9,
              background: isEditing ? "var(--primary)" : "var(--surface2)",
              color: isEditing ? "white" : "var(--label2)",
              fontSize: 12, fontWeight: 700,
              transition: "all 0.15s",
              minWidth: 44, minHeight: 32,
            }}
          >
            거래
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── 관심종목 탭 ──────────────────────────────────────────────────────────────

function WatchlistTab({ onAddToPortfolio, onSelectItem }: { onAddToPortfolio: (item: WatchlistItem) => void; onSelectItem: (item: WatchlistItem) => void }) {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [prices, setPrices] = useState<Record<string, StockPrice | null>>({});

  useEffect(() => { listWatchlist().then(setItems).catch(() => {}); }, []);

  useEffect(() => {
    items.forEach(item => {
      if (prices[item.stock_code] === undefined) {
        setPrices(prev => ({ ...prev, [item.stock_code]: null }));
        fetchStockPrice(item.stock_code).then(p => setPrices(prev => ({ ...prev, [item.stock_code]: p }))).catch(() => {});
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  useEffect(() => {
    const t = setTimeout(async () => {
      if (!query.trim()) { setSearchResults([]); return; }
      setSearching(true);
      try { setSearchResults((await searchStock(query)).slice(0, 5)); }
      catch { setSearchResults([]); }
      finally { setSearching(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  async function addItem(r: SearchResult) {
    await addWatchlistItem({ stock_code: r.stock_code, corp_name: r.corp_name });
    const updated = await listWatchlist();
    setItems(updated);
    setQuery(""); setSearchResults([]);
  }

  async function removeItem(stock_code: string) {
    await removeWatchlistItem(stock_code);
    setItems(prev => prev.filter(i => i.stock_code !== stock_code));
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* 검색 추가 */}
      <div style={{ padding: "12px 16px 0", flexShrink: 0 }}>
        <input type="text" value={query} onChange={e => setQuery(e.target.value)} placeholder="관심종목 추가…"
          style={{ width: "100%", background: "var(--surface)", borderRadius: 12, padding: "9px 14px", fontSize: 14, border: "0.5px solid var(--sep)", outline: "none", boxShadow: "var(--shadow-sm)" }} />
        {searching && <div style={{ fontSize: 12, color: "var(--label3)", textAlign: "center", marginTop: 6 }}>검색 중…</div>}
        {searchResults.length > 0 && (
          <div style={{ background: "var(--surface)", borderRadius: 12, overflow: "hidden", marginTop: 6, boxShadow: "var(--shadow)" }}>
            {searchResults.map((r, i) => (
              <div key={r.stock_code}>
                {i > 0 && <div style={{ height: "0.5px", background: "var(--sep)", marginLeft: 12 }} />}
                <button onClick={() => addItem(r)} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", padding: "10px 14px", textAlign: "left" }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{r.corp_name}</span>
                  <span style={{ fontSize: 12, color: "var(--primary)", fontWeight: 700 }}>+ 추가</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 관심종목 목록 */}
      {items.length === 0 ? (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1, padding: "40px 24px", gap: 20 }}>
          <div style={{
            width: 64, height: 64, borderRadius: 20,
            background: "var(--surface2)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--label3)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
            </svg>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: "var(--label)", marginBottom: 8 }}>관심 종목이 없어요</div>
            <div style={{ fontSize: 13, color: "var(--label3)", lineHeight: 1.7 }}>
              관심 종목을 추가하면<br />시세를 한눈에 확인할 수 있어요
            </div>
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, overflowY: "auto" }}>
          {items.map((item, i) => {
            const p = prices[item.stock_code];
            return (
              <div key={item.stock_code}>
                {i > 0 && <div style={{ height: "0.5px", background: "var(--sep)", marginLeft: 68 }} />}
                <div
                  style={{ display: "flex", alignItems: "center", padding: "11px 16px", gap: 12, cursor: "pointer" }}
                  onClick={() => onSelectItem(item)}
                >
                  <div style={{
                    width: 40, height: 40, borderRadius: 12,
                    background: "var(--surface2)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 16, fontWeight: 800, color: "var(--label2)", flexShrink: 0,
                  }}>
                    {item.corp_name.slice(0, 1)}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: "-0.02em" }}>{item.corp_name}</div>
                    <div style={{ fontSize: 11, color: "var(--label3)", marginTop: 1 }}>{item.stock_code}</div>
                  </div>
                  <div style={{ textAlign: "right", flexShrink: 0, minWidth: 72 }}>
                    {p ? (
                      <>
                        <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: "-0.03em" }}>{fmt(p.current_price)}</div>
                        <div style={{ fontSize: 11, fontWeight: 700, color: pctColor(p.change_pct) }}>{pctSign(p.change_pct)}</div>
                      </>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end" }}>
                        <div style={{ width: 54, height: 14, background: "var(--surface2)", borderRadius: 4, animation: "pulse 1.4s ease-in-out infinite" }} />
                        <div style={{ width: 38, height: 11, background: "var(--surface2)", borderRadius: 4, animation: "pulse 1.4s ease-in-out infinite", animationDelay: "0.1s" }} />
                      </div>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: 6, flexShrink: 0 }} onClick={e => e.stopPropagation()}>
                    <button
                      onClick={() => onAddToPortfolio(item)}
                      style={{
                        padding: "6px 12px", background: "rgba(0,122,255,0.09)", color: "var(--primary)",
                        borderRadius: 9, fontSize: 12, fontWeight: 700, minHeight: 32,
                      }}
                    >
                      매수
                    </button>
                    <button
                      onClick={() => removeItem(item.stock_code)}
                      className="touch-target"
                      style={{
                        width: 32, height: 32, borderRadius: "50%", background: "var(--surface2)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        color: "var(--label3)", fontSize: 12,
                      }}
                    >
                      ✕
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── 도넛 차트 ────────────────────────────────────────────────────────────────

const PALETTE = ["#007AFF", "#FF3B30", "#34C759", "#FF9500", "#AF52DE", "#FF2D55", "#00C7BE", "#5856D6"];

function DonutChart({ slices }: { slices: { label: string; pct: number; color: string }[] }) {
  const size = 140;
  const r = 52;
  const cx = size / 2;
  const cy = size / 2;
  let cumAngle = -90;
  const paths: { d: string; color: string }[] = [];

  for (const slice of slices) {
    const angle = (slice.pct / 100) * 360;
    const start = cumAngle;
    const end = cumAngle + angle;
    const startRad = (start * Math.PI) / 180;
    const endRad = (end * Math.PI) / 180;
    const x1 = cx + r * Math.cos(startRad);
    const y1 = cy + r * Math.sin(startRad);
    const x2 = cx + r * Math.cos(endRad);
    const y2 = cy + r * Math.sin(endRad);
    const largeArc = angle > 180 ? 1 : 0;
    paths.push({
      d: `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`,
      color: slice.color,
    });
    cumAngle += angle;
  }

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
      {slices.length === 1 ? (
        <circle cx={cx} cy={cy} r={r} fill={slices[0].color} opacity={0.88} />
      ) : (
        paths.map((p, i) => (
          <path key={i} d={p.d} fill={p.color} opacity={0.88} />
        ))
      )}
      <circle cx={cx} cy={cy} r={r * 0.58} fill="var(--surface)" />
    </svg>
  );
}

// ─── 배분 탭 ─────────────────────────────────────────────────────────────────

function AllocationTab({ items, prices }: { items: PortfolioItem[]; prices: Record<string, StockPrice> }) {
  if (items.length === 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1, padding: "40px 24px", gap: 20 }}>
        <div style={{
          width: 64, height: 64, borderRadius: 20,
          background: "var(--surface2)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--label3)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21.21 15.89A10 10 0 1 1 8 2.83" /><path d="M22 12A10 10 0 0 0 12 2v10z" />
          </svg>
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: "var(--label)", marginBottom: 8 }}>배분 데이터가 없어요</div>
          <div style={{ fontSize: 13, color: "var(--label3)", lineHeight: 1.7 }}>
            종목을 추가하면<br />포트폴리오 배분을 볼 수 있어요
          </div>
        </div>
      </div>
    );
  }

  const values = items.map(item => {
    const p = prices[item.stock_code];
    const val = p ? p.current_price * item.quantity : item.buy_price * item.quantity;
    const invested = item.buy_price * item.quantity;
    const pnl = val - invested;
    const pnlPct = invested > 0 ? (pnl / invested) * 100 : 0;
    return { ...item, currentValue: val, invested, pnl, pnlPct };
  });
  const total = values.reduce((s, v) => s + v.currentValue, 0);
  const totalInvested = values.reduce((s, v) => s + v.invested, 0);
  const totalPnl = total - totalInvested;
  const totalPnlPct = totalInvested > 0 ? (totalPnl / totalInvested) * 100 : 0;
  const isProfitOverall = totalPnl >= 0;

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
      {/* 포트폴리오 요약 스트립 */}
      <div style={{
        display: "flex", alignItems: "stretch",
        background: "var(--surface)", borderRadius: 16, padding: "12px 16px",
        boxShadow: "var(--shadow-sm)", marginBottom: 14,
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 3, fontWeight: 500 }}>총 평가금액</div>
          <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.04em" }}>{fmt(total)}원</div>
        </div>
        <div style={{ width: "0.5px", background: "var(--sep)", margin: "0 14px" }} />
        <div style={{ flex: 1, textAlign: "center" }}>
          <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 3, fontWeight: 500 }}>수익률</div>
          <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.04em", color: isProfitOverall ? "var(--red)" : "var(--primary)" }}>
            {totalPnlPct > 0 ? "+" : ""}{totalPnlPct.toFixed(2)}%
          </div>
        </div>
        <div style={{ width: "0.5px", background: "var(--sep)", margin: "0 14px" }} />
        <div style={{ flex: 1, textAlign: "right" }}>
          <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 3, fontWeight: 500 }}>손익</div>
          <div style={{ fontSize: 13, fontWeight: 700, color: isProfitOverall ? "var(--red)" : "var(--primary)" }}>
            {totalPnl > 0 ? "+" : ""}{fmt(totalPnl)}원
          </div>
        </div>
      </div>

      {/* 도넛 차트 */}
      {(() => {
        const sorted = [...values].sort((a, b) => b.currentValue - a.currentValue);
        const slices = sorted.map((v, i) => ({
          label: v.corp_name,
          pct: total > 0 ? (v.currentValue / total) * 100 : 0,
          color: PALETTE[i % PALETTE.length],
        }));
        const manyStocks = slices.length > 4;
        return (
          <div style={{ background: "var(--surface)", borderRadius: 16, padding: "14px 16px", boxShadow: "var(--shadow-sm)", marginBottom: 6 }}>
            <div style={{ display: "flex", flexDirection: manyStocks ? "column" : "row", alignItems: manyStocks ? "center" : "center", gap: 16 }}>
              <DonutChart slices={slices} />
              <div style={{
                flex: 1, width: manyStocks ? "100%" : undefined,
                display: "grid",
                gridTemplateColumns: manyStocks ? "1fr 1fr" : "1fr",
                gap: manyStocks ? "6px 12px" : 7,
              }}>
                {slices.map((s, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                    <div style={{ width: 8, height: 8, borderRadius: "50%", background: s.color, flexShrink: 0 }} />
                    <span style={{ fontSize: 12, fontWeight: 600, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.label}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "var(--label2)", flexShrink: 0 }}>{s.pct.toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        );
      })()}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {values
          .sort((a, b) => b.currentValue - a.currentValue)
          .map((v, idx) => {
            const pct = total > 0 ? (v.currentValue / total) * 100 : 0;
            const isProfit = v.pnlPct >= 0;
            const color = isProfit ? "var(--red)" : "var(--primary)";
            const dotColor = PALETTE[idx % PALETTE.length];
            return (
              <div key={v.stock_code} style={{ background: "var(--surface)", borderRadius: 16, padding: "13px 16px", boxShadow: "var(--shadow-sm)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: 9,
                      background: `${dotColor}18`,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 13, fontWeight: 800, color: dotColor,
                    }}>
                      {v.corp_name.slice(0, 1)}
                    </div>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: "-0.02em" }}>{v.corp_name}</div>
                      <div style={{ fontSize: 11, color: "var(--label3)", marginTop: 1 }}>{fmt(v.quantity)}주</div>
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 16, fontWeight: 800, letterSpacing: "-0.03em" }}>{pct.toFixed(1)}%</div>
                    <div style={{ fontSize: 11, color, fontWeight: 700 }}>{v.pnlPct > 0 ? "+" : ""}{v.pnlPct.toFixed(1)}%</div>
                  </div>
                </div>
                <div style={{ height: 7, background: "var(--bg)", borderRadius: 4, overflow: "hidden", marginBottom: 8 }}>
                  <div style={{
                    height: "100%", width: `${pct}%`,
                    background: dotColor, borderRadius: 4,
                    transition: "width 0.9s cubic-bezier(0.34,1.56,0.64,1)",
                    opacity: 0.75,
                  }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <div style={{ fontSize: 11, color: "var(--label3)" }}>{fmt(v.currentValue)}원</div>
                  <div style={{ fontSize: 11, fontWeight: 700, color }}>{v.pnl > 0 ? "+" : ""}{fmt(v.pnl)}원</div>
                </div>
              </div>
            );
          })}
      </div>
    </div>
  );
}

// ─── 포트폴리오 메인 ──────────────────────────────────────────────────────────

export function PortfolioCard({ onPortfolioChange }: { onPortfolioChange?: () => void } = {}) {
  const [activeTab, setActiveTab] = useState<Tab>("stocks");
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [selected, setSelected] = useState<PortfolioItem | null>(null);
  const [prices, setPrices] = useState<Record<string, StockPrice>>({});
  const [alerts, setAlerts] = useState<Record<string, number>>({});
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const [watchlistAdd, setWatchlistAdd] = useState<WatchlistItem | null>(null);
  const [watchlistSelected, setWatchlistSelected] = useState<WatchlistItem | null>(null);

  const stockCodes = useMemo(() => items.map(i => i.stock_code), [items]);
  const realtimePrices = useRealtimePrice(stockCodes);

  const mergedPrices = useMemo(() => {
    const merged = { ...prices };
    for (const [code, rt] of Object.entries(realtimePrices)) {
      if (merged[code]) merged[code] = { ...merged[code], current_price: rt.current_price, change_pct: rt.change_pct, change_amount: rt.change_amount, volume: rt.volume };
    }
    return merged;
  }, [prices, realtimePrices]);

  useEffect(() => {
    listPortfolio().then(setItems).catch(() => {});
    fetchPortfolioAlerts().then(setAlerts).catch(() => {});
  }, []);

  const handlePriceLoaded = useCallback((code: string, price: StockPrice) => {
    setPrices(prev => ({ ...prev, [code]: price }));
  }, []);

  async function handleAdd(item: PortfolioItem) {
    await addPortfolioItem(item);
    setItems(await listPortfolio());
    fetchPortfolioAlerts().then(setAlerts).catch(() => {});
    onPortfolioChange?.();
  }

  async function handleDelete(stock_code: string) {
    await removePortfolioItem(stock_code);
    setItems(prev => prev.filter(i => i.stock_code !== stock_code));
    setPrices(prev => { const { [stock_code]: _p, ...rest } = prev; return rest; });
    setAlerts(prev => { const { [stock_code]: _a, ...rest } = prev; return rest; });
    if (editingCode === stock_code) setEditingCode(null);
    onPortfolioChange?.();
  }

  async function handleEdit(stock_code: string, quantity: number, buyPrice: number) {
    const current = items.find(i => i.stock_code === stock_code);
    await updatePortfolioItem(stock_code, buyPrice, quantity, current?.target_price, current?.stop_loss);
    if (quantity <= 0) {
      setItems(prev => prev.filter(i => i.stock_code !== stock_code));
      setPrices(prev => { const { [stock_code]: _p, ...rest } = prev; return rest; });
    } else {
      setItems(prev => prev.map(i => i.stock_code === stock_code ? { ...i, quantity, buy_price: buyPrice } : i));
    }
    setEditingCode(null);
  }

  function handleModalEdit(stock_code: string, quantity: number, buyPrice: number, targetPrice?: number, stopLoss?: number) {
    if (quantity <= 0) {
      setItems(prev => prev.filter(i => i.stock_code !== stock_code));
      setPrices(prev => { const { [stock_code]: _p, ...rest } = prev; return rest; });
    } else {
      setItems(prev => prev.map(i => i.stock_code === stock_code
        ? { ...i, quantity, buy_price: buyPrice, target_price: targetPrice, stop_loss: stopLoss }
        : i,
      ));
    }
  }

  function handleWatchlistAddToPortfolio(item: WatchlistItem) {
    setWatchlistAdd(item);
    setShowAdd(true);
    setActiveTab("stocks");
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minHeight: 0 }}>
      <TabBar active={activeTab} onChange={t => { setActiveTab(t); setEditingCode(null); setShowAdd(false); }} />

      {/* 내 주식 탭 */}
      {activeTab === "stocks" && (
        <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column" }}>
          {items.length > 0 && <SummaryCard items={items} prices={mergedPrices} />}

          <div style={{ padding: "8px 16px 10px" }}>
            {!showAdd ? (
              <button onClick={() => setShowAdd(true)}
                style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, width: "100%", padding: "10px", background: "var(--primary)", color: "white", borderRadius: 12, fontSize: 13, fontWeight: 600 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M12 5V19M5 12H19" stroke="white" strokeWidth="2.5" strokeLinecap="round" /></svg>
                종목 추가
              </button>
            ) : (
              <AddStockPanel
                onAdd={handleAdd}
                onClose={() => { setShowAdd(false); setWatchlistAdd(null); }}
              />
            )}
          </div>

          {items.length === 0 && !showAdd && (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1, padding: "40px 24px", gap: 20 }}>
              <div style={{
                width: 64, height: 64, borderRadius: 20,
                background: "var(--surface2)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--label3)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 3v18h18" /><path d="M18 17V9" /><path d="M13 17V5" /><path d="M8 17v-3" />
                </svg>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: 16, fontWeight: 700, color: "var(--label)", marginBottom: 8 }}>보유 종목이 없어요</div>
                <div style={{ fontSize: 13, color: "var(--label3)", lineHeight: 1.7 }}>
                  위 종목 추가 버튼으로<br />실시간 시세와 AI 분석을 시작해보세요
                </div>
              </div>
            </div>
          )}

          {items.length > 0 && (
            <div style={{ flex: 1 }}>
              {items.map((item, i) => (
                <div key={item.stock_code}>
                  {i > 0 && editingCode !== items[i - 1]?.stock_code && (
                    <div style={{ height: "0.5px", background: "var(--sep)", marginLeft: 68 }} />
                  )}
                  <StockRow
                    item={item}
                    onClick={() => { setEditingCode(null); setSelected(item); }}
                    onEdit={() => setEditingCode(editingCode === item.stock_code ? null : item.stock_code)}
                    onPriceLoaded={handlePriceLoaded}
                    alertCount={alerts[item.stock_code] ?? 0}
                    realtimePrice={realtimePrices[item.stock_code]}
                    isEditing={editingCode === item.stock_code}
                  />
                  {editingCode === item.stock_code && (
                    <TradePanel
                      item={item}
                      onSave={(qty, price) => handleEdit(item.stock_code, qty, price)}
                      onDelete={() => handleDelete(item.stock_code)}
                      onCancel={() => setEditingCode(null)}
                    />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 관심종목 탭 */}
      {activeTab === "watchlist" && (
        <WatchlistTab onAddToPortfolio={handleWatchlistAddToPortfolio} onSelectItem={setWatchlistSelected} />
      )}

      {/* 배분 탭 */}
      {activeTab === "allocation" && (
        <AllocationTab items={items} prices={mergedPrices} />
      )}

      {/* 상세 모달 — 포트폴리오 종목 */}
      {selected && (
        <StockDetailModal
          item={selected}
          onClose={() => setSelected(null)}
          onEdit={(qty, price, tp, sl) => handleModalEdit(selected.stock_code, qty, price, tp, sl)}
        />
      )}

      {/* 상세 모달 — 관심종목 (보유 정보 없음) */}
      {watchlistSelected && (
        <StockDetailModal
          item={{ stock_code: watchlistSelected.stock_code, corp_name: watchlistSelected.corp_name, buy_price: 0, quantity: 0 }}
          onClose={() => setWatchlistSelected(null)}
        />
      )}
    </div>
  );
}

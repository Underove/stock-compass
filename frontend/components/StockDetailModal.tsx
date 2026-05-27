"use client";

import { useCallback, useEffect, useState } from "react";

import { addWatchlistItem, fetchChartData, fetchCommentary, fetchDisclosures, fetchFundamental, fetchNote, fetchShortSelling, fetchStockNews, fetchStockPrice, fetchTechnical, fetchTradingFlow, getSimilarStocks, removePortfolioItem, saveNote, updatePortfolioItem } from "../lib/api";
import { isAfterHours, isMarketOpen, isPreMarket, useRealtimePrice } from "../hooks/useRealtimePrice";
import { usePriceFlash } from "../hooks/usePriceFlash";
import type { Candle, CommentarySections, CrossStatus, DisclosureItem, FundamentalData, NewsItem, PortfolioItem, ShortSellingData, SimilarItem, StockPrice, TechnicalData, TradingFlowItem } from "../lib/types";
import { StockChart } from "./StockChart";
import { CompareModal } from "./CompareModal";

type Period = "1W" | "1M" | "3M" | "6M" | "1Y";
type Tab = "price" | "technical" | "ai";
const PERIOD_DAYS: Record<Period, number> = { "1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365 };

function fmt(n: number) { return n.toLocaleString("ko-KR"); }
function pctColor(pct: number) {
  if (pct > 0) return "var(--red)";
  if (pct < 0) return "var(--primary)";
  return "var(--label2)";
}
function pctSign(pct: number) {
  return pct > 0 ? `+${pct.toFixed(2)}%` : `${pct.toFixed(2)}%`;
}
function fmtMarketCap(n: number) {
  if (n >= 1e12) return `${(n / 1e12).toFixed(1)}조원`;
  if (n >= 1e8) return `${Math.round(n / 1e8).toLocaleString("ko-KR")}억원`;
  return `${fmt(n)}원`;
}
function fmtFlow(n: number) {
  const abs = Math.abs(n);
  if (abs >= 1e12) return `${(n / 1e12).toFixed(1)}조`;
  if (abs >= 1e8) return `${(n / 1e8).toFixed(0)}억`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(0)}백만`;
  return fmt(n);
}

type Props = {
  item: PortfolioItem;
  onClose: () => void;
  onEdit?: (quantity: number, buyPrice: number, targetPrice?: number, stopLoss?: number) => void;
};

export function StockDetailModal({ item, onClose, onEdit }: Props) {
  const [currentItem, setCurrentItem] = useState(item);
  const [compareOpen, setCompareOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("price");

  const [price, setPrice] = useState<StockPrice | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [period, setPeriod] = useState<Period>("3M");
  const [commentary, setCommentary] = useState<string | null>(null);
  const [commentarySections, setCommentarySections] = useState<CommentarySections | null>(null);
  const [technical, setTechnical] = useState<TechnicalData | null>(null);
  const [disclosures, setDisclosures] = useState<DisclosureItem[]>([]);
  const [loadingPrice, setLoadingPrice] = useState(true);
  const [loadingChart, setLoadingChart] = useState(true);
  const [loadingCommentary, setLoadingCommentary] = useState(true);
  const [loadingTechnical, setLoadingTechnical] = useState(true);
  const [loadingDisclosures, setLoadingDisclosures] = useState(true);
  const [fundamental, setFundamental] = useState<FundamentalData | null>(null);
  const [tradingFlow, setTradingFlow] = useState<TradingFlowItem[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [shortSelling, setShortSelling] = useState<ShortSellingData | null>(null);
  const [note, setNote] = useState("");
  const [loadingFundamental, setLoadingFundamental] = useState(true);
  const [loadingTradingFlow, setLoadingTradingFlow] = useState(true);
  const [loadingNews, setLoadingNews] = useState(true);
  const [loadingShortSelling, setLoadingShortSelling] = useState(true);

  const [editMode, setEditMode] = useState(false);
  const [editQty, setEditQty] = useState(item.quantity.toString());
  const [editPrice, setEditPrice] = useState(item.buy_price.toString());
  const [editTargetPrice, setEditTargetPrice] = useState(item.target_price?.toString() ?? "");
  const [editStopLoss, setEditStopLoss] = useState(item.stop_loss?.toString() ?? "");
  const [saving, setSaving] = useState(false);

  const [similarItems, setSimilarItems] = useState<SimilarItem[]>([]);
  const [watchlistAdded, setWatchlistAdded] = useState(false);
  const [simWatchlistAdded, setSimWatchlistAdded] = useState<Set<string>>(new Set());

  useEffect(() => {
    setWatchlistAdded(false);
    setSimWatchlistAdded(new Set());
  }, [currentItem.stock_code]);

  useEffect(() => {
    let ignore = false;
    getSimilarStocks(currentItem.stock_code)
      .then(data => { if (!ignore) setSimilarItems(data); })
      .catch(() => { if (!ignore) console.warn("유사종목 조회 실패"); });
    return () => { ignore = true; };
  }, [currentItem.stock_code]);

  // ── 가격: REST 초기 로드 + 장외 60초 폴링 ─────────────────────────────────
  const loadPrice = useCallback(async () => {
    try {
      const p = await fetchStockPrice(currentItem.stock_code);
      setPrice(p);
    } catch { /* ignore */ }
    finally { setLoadingPrice(false); }
  }, [currentItem.stock_code]);

  useEffect(() => {
    loadPrice();
    // 장중에는 WebSocket이 처리, REST는 open/high/low 동기화용으로만
    const interval = isMarketOpen() ? 60_000 : 60_000;
    const id = setInterval(loadPrice, interval);
    return () => clearInterval(id);
  }, [loadPrice]);

  // ── 가격: WebSocket 실시간 tick (정규장 한정) ──────────────────────────────
  const rtPrices = useRealtimePrice([currentItem.stock_code]);
  useEffect(() => {
    const rt = rtPrices[currentItem.stock_code];
    if (!rt) return;
    setPrice(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        current_price: rt.current_price,
        change_pct: rt.change_pct,
        change_amount: rt.change_amount,
        volume: rt.volume,
        high: Math.max(prev.high || 0, rt.current_price),
        low: prev.low > 0 ? Math.min(prev.low, rt.current_price) : rt.current_price,
        session: "open" as const,
      };
    });
    setLoadingPrice(false);
  }, [rtPrices, currentItem.stock_code]);

  // ── 차트 ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    setLoadingChart(true);
    fetchChartData(currentItem.stock_code, PERIOD_DAYS[period])
      .then(setCandles).catch(() => {}).finally(() => setLoadingChart(false));
  }, [currentItem.stock_code, period]);

  // ── 시황 해설: 최초 로드 + 정규장 중 3분마다 갱신 ─────────────────────────
  const loadCommentary = useCallback(async () => {
    setLoadingCommentary(true);
    try {
      const d = await fetchCommentary(currentItem.stock_code, currentItem.corp_name);
      setCommentary(d.commentary);
      setCommentarySections(d.commentary_sections ?? null);
    } catch { setCommentary(null); }
    finally { setLoadingCommentary(false); }
  }, [currentItem.stock_code, currentItem.corp_name]);

  useEffect(() => {
    loadCommentary();
  }, [loadCommentary]);

  // ── 기술지표: 최초 로드 + 정규장 5분 자동갱신 + 수동 새로고침 ──────────────
  const loadTechnical = useCallback(async () => {
    setLoadingTechnical(true);
    fetchTechnical(currentItem.stock_code)
      .then(setTechnical).catch(() => setTechnical(null))
      .finally(() => setLoadingTechnical(false));
  }, [currentItem.stock_code]);

  useEffect(() => {
    loadTechnical();
    if (!isMarketOpen()) return;
    const id = setInterval(loadTechnical, 5 * 60_000);
    return () => clearInterval(id);
  }, [loadTechnical]);

  useEffect(() => {
    setLoadingDisclosures(true);
    fetchDisclosures(currentItem.stock_code, 30)
      .then(setDisclosures).catch(() => setDisclosures([]))
      .finally(() => setLoadingDisclosures(false));
  }, [currentItem.stock_code]);

  useEffect(() => {
    setLoadingFundamental(true);
    setLoadingTradingFlow(true);
    setLoadingNews(true);
    setLoadingShortSelling(true);
    fetchFundamental(currentItem.stock_code)
      .then(setFundamental).catch(() => setFundamental(null))
      .finally(() => setLoadingFundamental(false));
    fetchTradingFlow(currentItem.stock_code)
      .then(d => setTradingFlow(d.flow)).catch(() => setTradingFlow([]))
      .finally(() => setLoadingTradingFlow(false));
    fetchStockNews(currentItem.stock_code, currentItem.corp_name)
      .then(d => setNews(d.news)).catch(() => setNews([]))
      .finally(() => setLoadingNews(false));
    fetchShortSelling(currentItem.stock_code)
      .then(setShortSelling).catch(() => setShortSelling(null))
      .finally(() => setLoadingShortSelling(false));
    fetchNote(currentItem.stock_code)
      .then(setNote).catch(() => setNote(""));
  }, [currentItem.stock_code, currentItem.corp_name]);

  const evalPnl = price !== null
    ? (price.current_price - currentItem.buy_price) * currentItem.quantity
    : null;
  const evalPnlPct = price !== null && currentItem.buy_price > 0
    ? ((price.current_price - currentItem.buy_price) / currentItem.buy_price) * 100
    : null;

  const todayStr = new Date(Date.now() + 9 * 60 * 60 * 1000).toISOString().slice(0, 10); // KST "YYYY-MM-DD"
  const isTradingHours = isMarketOpen() || isAfterHours() || isPreMarket();
  const liveCandle: Candle | undefined =
    price && isTradingHours && isFinite(price.open) && price.open > 0
      ? {
          time: todayStr,
          open: price.open,
          high: price.high,
          low: price.low,
          close: price.current_price,
          volume: price.volume,
        }
      : undefined;

  const sessionLabel =
    price?.session === "after" ? "시간외" :
    price?.session === "pre" ? "장전" : null;

  async function saveEdit() {
    const q = parseInt(editQty, 10);
    const p = parseInt(editPrice, 10);
    if (isNaN(q) || isNaN(p) || p <= 0) return;
    const tpRaw = editTargetPrice ? parseInt(editTargetPrice, 10) : undefined;
    const slRaw = editStopLoss ? parseInt(editStopLoss, 10) : undefined;
    const tp = tpRaw !== undefined && !isNaN(tpRaw) && tpRaw > 0 ? tpRaw : undefined;
    const sl = slRaw !== undefined && !isNaN(slRaw) && slRaw > 0 ? slRaw : undefined;
    setSaving(true);
    try {
      await updatePortfolioItem(currentItem.stock_code, p, q, tp, sl);
      if (q <= 0) {
        onEdit?.(0, p);
        onClose();
      } else {
        setCurrentItem(prev => ({ ...prev, quantity: q, buy_price: p, target_price: tp, stop_loss: sl }));
        onEdit?.(q, p, tp, sl);
        setEditMode(false);
      }
    } finally {
      setSaving(false);
    }
  }

  async function deleteItem() {
    setSaving(true);
    try {
      await removePortfolioItem(currentItem.stock_code);
      onEdit?.(0, 0);
      onClose();
    } finally {
      setSaving(false);
    }
  }

  const cp = price?.current_price ?? null;
  const heroFlash = usePriceFlash(cp);
  const isProfit = evalPnlPct !== null && evalPnlPct >= 0;

  return (
    <div style={{ position: "fixed", inset: 0, background: "var(--bg)", zIndex: 100, display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>

        {/* ── 상단 헤더 ── */}
        <div style={{
          padding: "14px 20px 12px",
          flexShrink: 0,
          borderBottom: "0.5px solid var(--sep)",
          background: "var(--bg)",
        }}>
          {/* 종목명 + 관심종목 + 닫기 */}
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 10 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, color: "var(--label3)", fontWeight: 500, marginBottom: 2, fontVariantNumeric: "tabular-nums" }}>
                {currentItem.stock_code}
              </div>
              <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.025em", lineHeight: 1.2 }}>
                {currentItem.corp_name}
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
              <button
                onClick={async () => {
                  if (watchlistAdded) return;
                  try {
                    await addWatchlistItem({ stock_code: currentItem.stock_code, corp_name: currentItem.corp_name });
                    setWatchlistAdded(true);
                  } catch {}
                }}
                style={{
                  width: 32, height: 32, borderRadius: "50%",
                  background: watchlistAdded ? "var(--primary)" : "var(--surface2)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  color: watchlistAdded ? "white" : "var(--label3)",
                  flexShrink: 0,
                  transition: "background 0.15s, color 0.15s",
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill={watchlistAdded ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                </svg>
              </button>
              <button
                onClick={() => setCompareOpen(true)}
                style={{
                  height: 32, borderRadius: 16, padding: "0 12px",
                  background: "var(--surface2)",
                  fontSize: 12, fontWeight: 700,
                  color: "var(--label2)", flexShrink: 0,
                  border: "none", cursor: "pointer",
                }}
              >
                비교
              </button>
              <button
                onClick={onClose}
                style={{
                  width: 32, height: 32, borderRadius: "50%",
                  background: "var(--surface2)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  color: "var(--label3)", flexShrink: 0,
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* 현재가 */}
          {loadingPrice ? (
            <Skeleton height={40} width="50%" />
          ) : price ? (
            <div style={{ display: "flex", alignItems: "flex-end", gap: 10, flexWrap: "wrap" }}>
              <div
                className={heroFlash ? `price-flash-${heroFlash}` : undefined}
                style={{ display: "flex", alignItems: "baseline", gap: 3 }}
              >
                <span style={{
                  fontSize: 30, fontWeight: 800,
                  letterSpacing: "-0.04em", lineHeight: 1,
                  color: pctColor(price.change_pct),
                  fontVariantNumeric: "tabular-nums",
                }}>
                  {fmt(price.current_price)}
                </span>
                <span style={{ fontSize: 14, fontWeight: 500, color: "var(--label3)", marginBottom: 3 }}>원</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, paddingBottom: 4 }}>
                <span style={{
                  fontSize: 13, fontWeight: 700, color: pctColor(price.change_pct),
                  background: isProfit ? "rgba(255,59,48,0.09)" : "rgba(0,122,255,0.09)",
                  borderRadius: 100, padding: "3px 10px",
                  fontVariantNumeric: "tabular-nums",
                }}>
                  {isFinite(price.change_amount) ? `${price.change_amount > 0 ? "+" : ""}${fmt(price.change_amount)}` : "—"} ({isFinite(price.change_pct) ? pctSign(price.change_pct) : "—"})
                </span>
                {sessionLabel && (
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 6,
                    background: sessionLabel === "시간외" ? "rgba(255,149,0,0.12)" : "rgba(90,200,250,0.15)",
                    color: sessionLabel === "시간외" ? "var(--orange)" : "#5AC8FA",
                  }}>
                    {sessionLabel}
                  </span>
                )}
              </div>
            </div>
          ) : (
            <div style={{ fontSize: 15, color: "var(--label3)" }}>시세 조회 불가</div>
          )}

          {/* 시가·고가·저가·거래량 mini row */}
          {price && (
            <div style={{ display: "flex", gap: 14, marginTop: 12, flexWrap: "wrap" }}>
              {[
                { label: "시가", value: fmt(price.open), color: "var(--label2)" },
                { label: "고가", value: fmt(price.high), color: "var(--red)" },
                { label: "저가", value: fmt(price.low), color: "var(--primary)" },
                { label: "거래량", value: price.volume ? `${(price.volume / 1000).toFixed(0)}K` : "—", color: "var(--label2)" },
              ].map(({ label, value, color }) => (
                <span key={label} style={{ fontSize: 11, color: "var(--label3)", display: "inline-flex", gap: 4 }}>
                  {label}
                  <span style={{ color, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{value}</span>
                </span>
              ))}
            </div>
          )}
        </div>

        {/* ── 포지션 요약 (포트폴리오 종목만) ── */}
        {currentItem.quantity > 0 && (
          <div style={{
            display: "flex", alignItems: "center", padding: "10px 20px 12px",
            borderBottom: "0.5px solid var(--sep)", flexShrink: 0,
          }}>
            <div style={{ flex: 1, display: "flex", gap: 0 }}>
              <StatCol label="보유" value={`${fmt(currentItem.quantity)}주`} />
              <Divider />
              <StatCol label="단가" value={`${fmt(currentItem.buy_price)}원`} center />
              {evalPnl !== null && evalPnlPct !== null && (
                <>
                  <Divider />
                  <div style={{ flex: 1, textAlign: "right" }}>
                    <div style={{ fontSize: 11, color: "var(--label3)", marginBottom: 4, fontWeight: 500 }}>손익</div>
                    <div style={{
                      fontSize: 13, fontWeight: 700, color: pctColor(evalPnlPct),
                      fontVariantNumeric: "tabular-nums",
                    }}>
                      {evalPnl > 0 ? "+" : ""}{fmt(evalPnl)}원 <span style={{ fontSize: 12 }}>({pctSign(evalPnlPct)})</span>
                    </div>
                  </div>
                </>
              )}
            </div>
            <button
              onClick={() => { setEditMode(true); setEditQty(currentItem.quantity.toString()); setEditPrice(currentItem.buy_price.toString()); setEditTargetPrice(currentItem.target_price?.toString() ?? ""); setEditStopLoss(currentItem.stop_loss?.toString() ?? ""); }}
              style={{
                fontSize: 12, color: "var(--label2)", fontWeight: 700,
                padding: "5px 12px", background: "var(--surface2)", borderRadius: 100,
                flexShrink: 0, marginLeft: 12,
              }}
            >
              수정
            </button>
          </div>
        )}

        {/* ── 탭 바 — iOS 세그먼트 ── */}
        <div style={{ padding: "8px 16px 7px", flexShrink: 0, borderBottom: "0.5px solid var(--sep)", background: "var(--bg)" }}>
          <div style={{ display: "flex", background: "var(--surface2)", borderRadius: 11, padding: 2 }}>
            {([["price", "시세"], ["technical", "기술 지표"], ["ai", "공시"]] as [Tab, string][]).map(([tab, label]) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  flex: 1, padding: "7px 4px",
                  fontSize: 13, fontWeight: activeTab === tab ? 700 : 500,
                  color: activeTab === tab ? "var(--label)" : "var(--label3)",
                  background: activeTab === tab ? "var(--surface)" : "transparent",
                  borderRadius: 9,
                  boxShadow: activeTab === tab ? "0 1px 4px rgba(0,0,0,0.10)" : "none",
                  transition: "all 0.18s",
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* ── 스크롤 본문 ── */}
        <div style={{ flex: 1, overflowY: "auto", WebkitOverflowScrolling: "touch" as const }}>

          {/* ────────── 시세 탭 ────────── */}
          {activeTab === "price" && (
            <div style={{ display: "flex", flexDirection: "column" }}>

              {editMode ? (
                /* ── 수정 모드 전체 화면 ── */
                <div style={{ padding: "16px 16px 48px" }}>
                  <div style={{ background: "var(--surface)", borderRadius: 20, padding: "18px 20px", boxShadow: "var(--shadow)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                      <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: "-0.022em" }}>보유 현황 수정</span>
                      <button onClick={() => setEditMode(false)} style={{ fontSize: 13, color: "var(--label2)", padding: "5px 12px", background: "var(--surface2)", borderRadius: 100, fontWeight: 700, letterSpacing: "-0.01em" }}>취소</button>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      <div style={{ display: "flex", gap: 8 }}>
                        <EditField label="수량 (주)" value={editQty} onChange={setEditQty} />
                        <EditField label="단가 (원)" value={editPrice} onChange={setEditPrice} />
                      </div>
                      <div style={{ display: "flex", gap: 8 }}>
                        <EditField label="목표가 (선택)" value={editTargetPrice} onChange={setEditTargetPrice} placeholder="미설정" accentColor="var(--red)" />
                        <EditField label="손절가 (선택)" value={editStopLoss} onChange={setEditStopLoss} placeholder="미설정" accentColor="var(--primary)" />
                      </div>
                      <button
                        onClick={saveEdit}
                        disabled={saving || !editQty || !editPrice}
                        style={{ width: "100%", padding: "14px", background: saving ? "var(--label3)" : "var(--primary)", color: "white", borderRadius: 14, fontSize: 16, fontWeight: 700, letterSpacing: "-0.015em" }}
                      >
                        {saving ? "저장 중…" : "저장"}
                      </button>
                      <button
                        onClick={deleteItem}
                        disabled={saving}
                        style={{ width: "100%", padding: "13px", background: "rgba(255,59,48,0.07)", color: "var(--red)", borderRadius: 14, fontSize: 15, fontWeight: 700, letterSpacing: "-0.015em" }}
                      >
                        종목 삭제
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  {/* ── 차트 히어로 ── */}
                  <div style={{ background: "var(--surface)", padding: "12px 16px 10px", borderBottom: "0.5px solid var(--sep)" }}>
                    {/* 기간 선택 */}
                    <div style={{ display: "flex", gap: 0, background: "var(--bg)", borderRadius: 100, padding: 3, marginBottom: 12, alignSelf: "flex-start" }}>
                      {(["1W", "1M", "3M", "6M", "1Y"] as Period[]).map(p => (
                        <button
                          key={p}
                          onClick={() => setPeriod(p)}
                          style={{
                            padding: "5px 10px", borderRadius: 100, fontSize: 12, fontWeight: period === p ? 700 : 500,
                            background: period === p ? "var(--surface)" : "transparent",
                            color: period === p ? "var(--label)" : "var(--label3)",
                            boxShadow: period === p ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
                            transition: "all 0.15s",
                            letterSpacing: "-0.01em",
                          }}
                        >
                          {p}
                        </button>
                      ))}
                    </div>

                    {/* 차트 본체 */}
                    {loadingChart ? (
                      <Skeleton height={240} />
                    ) : candles.length > 0 ? (
                      <StockChart candles={candles} height={240} buyPrice={currentItem.buy_price} liveCandle={liveCandle} />
                    ) : (
                      <div style={{ height: 240, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--label2)", fontSize: 14 }}>
                        차트 데이터가 없어요
                      </div>
                    )}

                    {/* 캔들 범례 */}
                    <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
                      <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 10, color: "var(--label3)" }}>
                        <span style={{ width: 7, height: 7, borderRadius: 2, background: "var(--red)", display: "inline-block" }} />상승
                      </span>
                      <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 10, color: "var(--label3)" }}>
                        <span style={{ width: 7, height: 7, borderRadius: 2, background: "var(--primary)", display: "inline-block" }} />하락
                      </span>
                    </div>
                  </div>


                  {/* ── 목표가 / 손절가 ── */}
                  {(currentItem.target_price || currentItem.stop_loss) && cp && (
                    <div style={{ background: "var(--bg)", display: "flex", gap: 8, padding: "10px 16px 0" }}>
                      {currentItem.target_price && (
                        <PriceGoalBar
                          label="목표가"
                          goalPrice={currentItem.target_price}
                          currentPrice={cp}
                          buyPrice={currentItem.buy_price}
                          type="target"
                        />
                      )}
                      {currentItem.stop_loss && (
                        <PriceGoalBar
                          label="손절가"
                          goalPrice={currentItem.stop_loss}
                          currentPrice={cp}
                          buyPrice={currentItem.buy_price}
                          type="stop"
                        />
                      )}
                    </div>
                  )}

                  {/* ── AI 시황 해설 ── */}
                  <div style={{ padding: "10px 16px 40px" }}>
                    <CommentaryCard
                      sections={commentarySections}
                      fallback={commentary}
                      loading={loadingCommentary}
                      onRefresh={loadCommentary}
                    />
                  </div>
                </>
              )}
            </div>
          )}

          {/* ────────── 기술 지표 탭 ────────── */}
          {activeTab === "technical" && (
            <div style={{ padding: "16px 16px 48px", display: "flex", flexDirection: "column", gap: 10 }}>

              {/* ── 재무 지표 ── */}
              {loadingFundamental ? (
                <div style={{ background: "var(--surface)", borderRadius: 20, padding: "16px 18px", boxShadow: "var(--shadow)" }}>
                  <Skeleton height={14} width="30%" />
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 12 }}>
                    {[1,2,3,4].map(i => <Skeleton key={i} height={60} />)}
                  </div>
                </div>
              ) : fundamental ? (
                <div style={{ background: "var(--surface)", borderRadius: 20, padding: "16px 18px", boxShadow: "var(--shadow)" }}>
                  <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "-0.02em", marginBottom: 12 }}>재무 지표</div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                    {([
                      { label: "PER", value: fundamental.per !== null ? `${fundamental.per.toFixed(1)}배` : "—", note: "주가 / 순이익", accent: "rgba(0,122,255,0.08)", dot: "var(--primary)" },
                      { label: "PBR", value: fundamental.pbr !== null ? `${fundamental.pbr.toFixed(2)}배` : "—", note: "주가 / 순자산", accent: "rgba(88,86,214,0.08)", dot: "#5856D6" },
                      { label: "EPS", value: fundamental.eps !== null ? `${fmt(Math.round(fundamental.eps))}원` : "—", note: "주당순이익", accent: "rgba(52,199,89,0.08)", dot: "var(--green)" },
                      { label: "배당수익률", value: fundamental.div !== null ? `${fundamental.div.toFixed(2)}%` : "—", note: "연간 배당 / 주가", accent: "rgba(255,149,0,0.08)", dot: "var(--orange)" },
                    ] as { label: string; value: string; note: string; accent: string; dot: string }[]).map(({ label, value, note, accent, dot }) => (
                      <div key={label} style={{ background: accent, borderRadius: 14, padding: "12px 13px", border: `0.5px solid ${dot}20` }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 6 }}>
                          <div style={{ width: 5, height: 5, borderRadius: "50%", background: dot, flexShrink: 0 }} />
                          <span style={{ fontSize: 11, color: "var(--label2)", fontWeight: 600 }}>{label}</span>
                        </div>
                        <div style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.03em", color: value === "—" ? "var(--label3)" : "var(--label)" }}>{value}</div>
                        <div style={{ fontSize: 10, color: "var(--label3)", marginTop: 3 }}>{note}</div>
                      </div>
                    ))}
                  </div>
                  {fundamental.market_cap !== null && (
                    <div style={{ marginTop: 12, paddingTop: 12, borderTop: "0.5px solid var(--sep)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 12, color: "var(--label3)", fontWeight: 500 }}>시가총액</span>
                      <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: "-0.02em" }}>{fmtMarketCap(fundamental.market_cap)}</span>
                    </div>
                  )}
                </div>
              ) : null}

              {/* ── 외인·기관 순매수 ── */}
              {loadingTradingFlow ? (
                <div style={{ background: "var(--surface)", borderRadius: 20, padding: "16px 18px", boxShadow: "var(--shadow)" }}>
                  <Skeleton height={14} width="40%" />
                  <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                    <Skeleton height={100} /><Skeleton height={100} />
                  </div>
                </div>
              ) : tradingFlow.length > 0 ? (
                <div style={{ background: "var(--surface)", borderRadius: 20, padding: "16px 18px", boxShadow: "var(--shadow)" }}>
                  <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "-0.02em", marginBottom: 12 }}>외인·기관 순매수</div>
                  <div style={{ display: "flex", gap: 12, paddingTop: 12, borderTop: "0.5px solid var(--sep)" }}>
                    {([["외국인", "foreign_net"], ["기관", "institution_net"]] as [string, keyof TradingFlowItem][]).map(([label, key]) => (
                      <div key={label} style={{ flex: 1 }}>
                        <div style={{ fontSize: 11, color: "var(--label3)", fontWeight: 600, marginBottom: 8 }}>{label}</div>
                        {tradingFlow.map((item, i) => {
                          const val = item[key] as number;
                          const color = val > 0 ? "var(--red)" : val < 0 ? "var(--primary)" : "var(--label3)";
                          return (
                            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                              <span style={{ fontSize: 10, color: "var(--label3)" }}>{item.date}</span>
                              <span style={{ fontSize: 12, fontWeight: 700, color }}>{val > 0 ? "+" : ""}{fmtFlow(val)}</span>
                            </div>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {/* ── 공매도 비율 ── */}
              {loadingShortSelling ? (
                <div style={{ background: "var(--surface)", borderRadius: 20, padding: "16px 18px", boxShadow: "var(--shadow)" }}>
                  <Skeleton height={14} width="30%" />
                  <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                    {[1,2,3,4,5].map(i => <Skeleton key={i} height={40} />)}
                  </div>
                </div>
              ) : shortSelling && (shortSelling.ratio !== null || shortSelling.trend.length > 0) ? (
                <div style={{ background: "var(--surface)", borderRadius: 20, padding: "16px 18px", boxShadow: "var(--shadow)" }}>
                  <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "-0.02em", marginBottom: 12 }}>공매도 비율</div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 0 12px", borderTop: "0.5px solid var(--sep)" }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
                      <span style={{ fontSize: 24, fontWeight: 800, letterSpacing: "-0.04em", color: (shortSelling.ratio ?? 0) > 5 ? "var(--red)" : "var(--label)" }}>
                        {shortSelling.ratio !== null ? shortSelling.ratio.toFixed(1) : "—"}
                      </span>
                      <span style={{ fontSize: 13, color: "var(--label3)" }}>%</span>
                    </div>
                    {shortSelling.ratio !== null && (
                      <div style={{
                        fontSize: 11, fontWeight: 700,
                        color: shortSelling.ratio > 5 ? "var(--red)" : shortSelling.ratio > 2 ? "var(--label2)" : "var(--primary)",
                        background: shortSelling.ratio > 5 ? "rgba(255,59,48,0.08)" : shortSelling.ratio > 2 ? "var(--surface2)" : "rgba(0,122,255,0.08)",
                        borderRadius: 8, padding: "4px 10px",
                      }}>
                        {shortSelling.ratio > 5 ? "높음" : shortSelling.ratio > 2 ? "보통" : "낮음"}
                      </div>
                    )}
                  </div>
                  {shortSelling.trend.length > 0 && (
                    <div style={{ display: "flex", gap: 4 }}>
                      {shortSelling.trend.map((t, i) => {
                        const maxRatio = Math.max(...shortSelling.trend.map(x => x.ratio), 0.1);
                        const barH = Math.max(4, (t.ratio / maxRatio) * 48);
                        const barColor = t.ratio > 5 ? "var(--red)" : t.ratio > 2 ? "var(--label3)" : "var(--primary)";
                        return (
                          <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                            <div style={{ width: "100%", height: 48, display: "flex", alignItems: "flex-end" }}>
                              <div style={{ width: "100%", height: barH, background: barColor, borderRadius: 4, opacity: 0.75 }} />
                            </div>
                            <div style={{ fontSize: 9, color: "var(--label3)" }}>{t.date}</div>
                            <div style={{ fontSize: 9, fontWeight: 700, color: barColor }}>{t.ratio.toFixed(1)}%</div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              ) : null}

              {/* ── 기술적 지표 ── */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "4px 2px 0" }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: "var(--label)" }}>기술적 지표</span>
                <button
                  onClick={loadTechnical}
                  disabled={loadingTechnical}
                  style={{ fontSize: 11, color: "var(--primary)", fontWeight: 700, padding: "5px 12px", background: "rgba(0,122,255,0.09)", borderRadius: 9, border: "none", cursor: "pointer" }}
                >
                  {loadingTechnical ? "…" : "새로고침"}
                </button>
              </div>
              {loadingTechnical ? (
                <TechnicalSkeleton />
              ) : technical ? (
                <TechnicalSection ta={technical} currentPrice={price?.current_price ?? technical.current_price} />
              ) : (
                <div style={{ background: "var(--surface)", borderRadius: 20, padding: "24px", textAlign: "center", color: "var(--label2)", fontSize: 14, boxShadow: "var(--shadow)" }}>
                  지표를 불러오지 못했습니다.
                </div>
              )}
            </div>
          )}

          {/* ────────── 공시 탭 ────────── */}
          {activeTab === "ai" && (
            <div style={{ padding: "16px 16px 48px", display: "flex", flexDirection: "column", gap: 10 }}>

              {/* 종목 메모 */}
              <div style={{ background: "var(--surface)", borderRadius: 20, overflow: "hidden", boxShadow: "var(--shadow)" }}>
                <div style={{ padding: "14px 18px 12px", borderBottom: "0.5px solid var(--sep)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 14, fontWeight: 700, letterSpacing: "-0.02em" }}>종목 메모</span>
                  <span style={{ fontSize: 11, color: "var(--label3)", fontWeight: 500 }}>자동 저장</span>
                </div>
                <div style={{ padding: "12px 18px 16px" }}>
                  <textarea
                    value={note}
                    onChange={e => setNote(e.target.value)}
                    onBlur={() => saveNote(currentItem.stock_code, note).catch(() => {})}
                    placeholder="매수 이유, 전략, 주의사항 등을 메모하세요…"
                    rows={4}
                    style={{
                      width: "100%", background: "var(--bg)", borderRadius: 12,
                      padding: "10px 14px", fontSize: 13, lineHeight: 1.7,
                      color: "var(--label)", border: "none", outline: "none",
                      resize: "none", fontFamily: "inherit",
                    }}
                  />
                </div>
              </div>

              {/* 관련 뉴스 */}
              <div style={{ background: "var(--surface)", borderRadius: 20, overflow: "hidden", boxShadow: "var(--shadow)" }}>
                <div style={{ padding: "14px 18px 12px", borderBottom: "0.5px solid var(--sep)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 14, fontWeight: 700 }}>관련 뉴스</span>
                </div>
                {loadingNews ? (
                  <div style={{ padding: "10px 18px", display: "flex", flexDirection: "column", gap: 8 }}>
                    <Skeleton height={52} /><Skeleton height={52} /><Skeleton height={52} />
                  </div>
                ) : news.length === 0 ? (
                  <div style={{ padding: "24px 18px", textAlign: "center", color: "var(--label2)", fontSize: 14 }}>
                    관련 뉴스가 없어요
                  </div>
                ) : (
                  <div>
                    {news.slice(0, 6).map((n, i) => (
                      <div key={i}>
                        {i > 0 && <div style={{ height: "0.5px", background: "var(--sep)", marginLeft: 18 }} />}
                        <a
                          href={n.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ display: "flex", alignItems: "flex-start", padding: "12px 18px", gap: 12, textDecoration: "none" }}
                        >
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{
                              fontSize: 13, color: "var(--label)", lineHeight: 1.45, fontWeight: 600,
                              overflow: "hidden", display: "-webkit-box",
                              WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
                            }}>
                              {n.title}
                            </div>
                            {n.description && (
                              <div style={{
                                fontSize: 12, color: "var(--label3)", marginTop: 3, lineHeight: 1.4,
                                overflow: "hidden", display: "-webkit-box",
                                WebkitLineClamp: 1, WebkitBoxOrient: "vertical",
                              }}>
                                {n.description}
                              </div>
                            )}
                          </div>
                          <div style={{ flexShrink: 0, textAlign: "right" }}>
                            <div style={{
                              fontSize: 11, fontWeight: 600, color: "var(--label3)",
                              background: "var(--surface2)", borderRadius: 7, padding: "3px 8px",
                              whiteSpace: "nowrap",
                            }}>
                              {n.date}
                            </div>
                          </div>
                        </a>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* 최근 공시 */}
              <div style={{ background: "var(--surface)", borderRadius: 20, overflow: "hidden", boxShadow: "var(--shadow)" }}>
                <div style={{ padding: "14px 18px 12px", borderBottom: "0.5px solid var(--sep)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 14, fontWeight: 700 }}>최근 공시</span>
                  <span style={{ fontSize: 12, color: "var(--label3)" }}>30일 이내</span>
                </div>
                {loadingDisclosures ? (
                  <div style={{ padding: "10px 18px", display: "flex", flexDirection: "column", gap: 8 }}>
                    <Skeleton height={44} /><Skeleton height={44} /><Skeleton height={44} />
                  </div>
                ) : disclosures.length === 0 ? (
                  <div style={{ padding: "24px 18px", textAlign: "center", color: "var(--label2)", fontSize: 14 }}>
                    최근 30일간 공시가 없어요
                  </div>
                ) : (
                  <div>
                    {disclosures.slice(0, 8).map((d, i) => (
                      <div key={d.rcept_no}>
                        {i > 0 && <div style={{ height: "0.5px", background: "var(--sep)", marginLeft: 18 }} />}
                        <a
                          href={d.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ display: "flex", alignItems: "center", padding: "12px 18px", gap: 12, textDecoration: "none" }}
                        >
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{
                              fontSize: 13, color: "var(--label)", lineHeight: 1.45, fontWeight: 600,
                              overflow: "hidden", display: "-webkit-box",
                              WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
                            }}>
                              {d.report_nm}
                            </div>
                            <div style={{ fontSize: 11, color: "var(--label3)", marginTop: 3 }}>{d.flr_nm}</div>
                          </div>
                          <div style={{ flexShrink: 0, textAlign: "right" }}>
                            <div style={{
                              fontSize: 11, fontWeight: 600, color: "var(--label3)",
                              background: "var(--surface2)", borderRadius: 7, padding: "3px 8px",
                              whiteSpace: "nowrap",
                            }}>
                              {d.rcept_dt.replace(/(\d{4})(\d{2})(\d{2})/, "$2/$3")}
                            </div>
                          </div>
                        </a>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 유사종목 */}
          {similarItems.length > 0 && (
            <div style={{ padding: "0 16px 16px" }}>
              <p style={{ fontSize: 11, color: "var(--label2)", fontWeight: 600, margin: "0 0 8px" }}>
                유사종목
              </p>
              <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 4 }}>
                {similarItems.map(sim => {
                  const isAdded = simWatchlistAdded.has(sim.stock_code);
                  return (
                    <div
                      key={sim.stock_code}
                      style={{
                        flexShrink: 0,
                        padding: "8px 10px 8px 12px",
                        borderRadius: 12,
                        background: "var(--surface3)",
                        border: "1px solid var(--sep)",
                        display: "flex", flexDirection: "column", gap: 6,
                        cursor: "pointer",
                      }}
                      onClick={() => {
                        setCurrentItem({ stock_code: sim.stock_code, corp_name: sim.corp_name, buy_price: 0, quantity: 0 });
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--label)" }}>{sim.corp_name}</span>
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            if (isAdded) return;
                            try {
                              await addWatchlistItem({ stock_code: sim.stock_code, corp_name: sim.corp_name });
                              setSimWatchlistAdded(prev => new Set([...prev, sim.stock_code]));
                            } catch {}
                          }}
                          style={{
                            width: 22, height: 22, borderRadius: "50%",
                            background: isAdded ? "var(--primary)" : "var(--surface2)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            color: isAdded ? "white" : "var(--label3)",
                            flexShrink: 0,
                            transition: "background 0.15s, color 0.15s",
                          }}
                        >
                          <svg width="10" height="10" viewBox="0 0 24 24" fill={isAdded ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                          </svg>
                        </button>
                      </div>
                      <span style={{ fontSize: 10, fontWeight: 600, color: "var(--label2)" }}>
                        {sim.sector}
                        {sim.per != null ? ` · PER ${sim.per}` : ""}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
      {compareOpen && (
        <CompareModal
          initialCode={currentItem.stock_code}
          initialName={currentItem.corp_name}
          onClose={() => setCompareOpen(false)}
        />
      )}
    </div>
  );
}

// ─── 서브 컴포넌트 ────────────────────────────────────────────────────────────

function StatCol({ label, value, center, right }: { label: string; value: string; center?: boolean; right?: boolean }) {
  return (
    <div style={{ flex: 1, textAlign: center ? "center" : right ? "right" : "left" }}>
      <div style={{ fontSize: 11, color: "var(--label3)", marginBottom: 4, fontWeight: 500 }}>{label}</div>
      <div style={{ fontSize: 13, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{value}</div>
    </div>
  );
}

function Divider() {
  return <div style={{ width: "0.5px", background: "var(--sep)", margin: "4px 0", alignSelf: "stretch" }} />;
}

function EditField({ label, value, onChange, placeholder, accentColor }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; accentColor?: string;
}) {
  const num = value !== "" ? parseInt(value, 10) : NaN;
  const display = !isNaN(num) ? num.toLocaleString("ko-KR") : "";
  return (
    <div style={{ flex: 1 }}>
      <div style={{ fontSize: 11, color: "var(--label2)", marginBottom: 5, fontWeight: 500 }}>{label}</div>
      <input
        type="text"
        inputMode="numeric"
        value={display}
        onChange={e => onChange(e.target.value.replace(/,/g, "").replace(/[^0-9]/g, ""))}
        placeholder={placeholder}
        style={{
          width: "100%", background: "var(--bg)", borderRadius: 10, padding: "10px 12px",
          fontSize: 15, border: "none", outline: "none",
          color: accentColor && value ? accentColor : "var(--label)",
        }}
      />
    </div>
  );
}

function PriceGoalBar({ label, goalPrice, currentPrice, buyPrice, type }: {
  label: string; goalPrice: number; currentPrice: number; buyPrice: number; type: "target" | "stop";
}) {
  const isTarget = type === "target";
  const color = isTarget ? "var(--red)" : "var(--primary)";
  const bg = isTarget ? "rgba(255,59,48,0.07)" : "rgba(0,122,255,0.07)";
  const diffPct = currentPrice > 0 ? ((goalPrice - currentPrice) / currentPrice * 100) : null;
  const achieved = isTarget ? currentPrice >= goalPrice : currentPrice <= goalPrice;

  const rangeMin = Math.min(buyPrice, currentPrice, goalPrice) * 0.98;
  const rangeMax = Math.max(buyPrice, currentPrice, goalPrice) * 1.02;
  const range = rangeMax - rangeMin;
  const posCurrent = range > 0 ? ((currentPrice - rangeMin) / range) * 100 : 50;
  const posGoal = range > 0 ? ((goalPrice - rangeMin) / range) * 100 : 50;

  return (
    <div style={{ flex: 1, background: bg, borderRadius: 14, padding: "12px 14px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ fontSize: 11, color, fontWeight: 700 }}>{label}</div>
        {achieved && (
          <div style={{ fontSize: 10, color, fontWeight: 700, background: `${color}18`, borderRadius: 4, padding: "2px 6px" }}>
            {isTarget ? "도달" : "손절"}
          </div>
        )}
      </div>
      <div style={{ fontSize: 16, fontWeight: 800, color, letterSpacing: "-0.03em" }}>
        {fmt(goalPrice)}<span style={{ fontSize: 11, fontWeight: 500, color: "var(--label3)", marginLeft: 2 }}>원</span>
      </div>
      <div style={{ fontSize: 11, color: "var(--label3)", marginTop: 2 }}>
        {diffPct !== null ? `${diffPct > 0 ? "+" : ""}${diffPct.toFixed(1)}%` : "—"}
      </div>
      {/* mini progress */}
      <div style={{ position: "relative", height: 4, background: "rgba(0,0,0,0.06)", borderRadius: 2, marginTop: 8 }}>
        <div style={{
          position: "absolute", top: "50%", transform: "translate(-50%,-50%)",
          left: `${Math.min(94, Math.max(6, posCurrent))}%`,
          width: 10, height: 10, borderRadius: "50%",
          background: "white", border: `2px solid ${pctColor(((currentPrice - buyPrice) / buyPrice) * 100)}`,
          boxShadow: "0 1px 4px rgba(0,0,0,0.2)",
        }} />
        <div style={{
          position: "absolute", top: "50%", transform: "translate(-50%,-50%)",
          left: `${Math.min(94, Math.max(6, posGoal))}%`,
          width: 8, height: 8, borderRadius: "50%",
          background: color, opacity: 0.5,
        }} />
      </div>
    </div>
  );
}

function Skeleton({ height, width = "100%" }: { height: number; width?: string }) {
  return (
    <div style={{ width, height, background: "var(--surface3)", borderRadius: 6, animation: "pulse 1.4s ease-in-out infinite" }} />
  );
}

function TechnicalSkeleton() {
  return (
    <>
      <div style={{ background: "var(--surface)", borderRadius: 20, padding: "16px", boxShadow: "var(--shadow)", display: "flex", gap: 8 }}>
        {[1, 2, 3].map(i => <Skeleton key={i} height={60} />)}
      </div>
      <div style={{ background: "var(--surface)", borderRadius: 20, padding: "20px", boxShadow: "var(--shadow)", display: "flex", flexDirection: "column", gap: 10 }}>
        <Skeleton height={16} width="40%" /><Skeleton height={48} /><Skeleton height={16} width="60%" />
      </div>
    </>
  );
}

// ─── 기술적 지표 섹션 ─────────────────────────────────────────────────────────

const CROSS_LABEL: Record<CrossStatus, { text: string; color: string }> = {
  golden: { text: "단기 상승 신호", color: "var(--red)" },
  dead:   { text: "단기 하락 신호", color: "var(--primary)" },
  above:  { text: "상승 흐름",      color: "var(--red)" },
  below:  { text: "하락 흐름",      color: "var(--primary)" },
  none:   { text: "보통",           color: "var(--label3)" },
};

function SignalRow({ title, status, value, color, muted }: {
  title: string; status: string; value?: string; color: string; muted?: boolean;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 0" }}>
      <div style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
      <span style={{ fontSize: 13, color: "var(--label3)", minWidth: 72, fontWeight: 500 }}>{title}</span>
      <span style={{ fontSize: 13, fontWeight: 700, color: muted ? "var(--label)" : color, flex: 1 }}>{status}</span>
      {value && <span style={{ fontSize: 12, color: "var(--label3)", fontWeight: 600 }}>{value}</span>}
    </div>
  );
}

function RangeBar({ pct, colorHigh = "var(--red)", colorLow = "var(--primary)" }: {
  pct: number; colorHigh?: string; colorLow?: string;
}) {
  const clampedPct = Math.min(95, Math.max(5, pct));
  const dotColor = pct > 70 ? colorHigh : pct < 30 ? colorLow : "var(--green)";
  return (
    <div style={{ position: "relative", height: 6, background: "var(--bg)", borderRadius: 3 }}>
      <div style={{
        position: "absolute", top: "50%", transform: "translate(-50%,-50%)",
        left: `${clampedPct}%`,
        width: 12, height: 12, borderRadius: "50%",
        background: dotColor, border: "2px solid white", boxShadow: "0 1px 4px rgba(0,0,0,0.2)",
      }} />
    </div>
  );
}

function TechnicalSection({ ta, currentPrice }: { ta: TechnicalData; currentPrice: number }) {
  const cp = currentPrice;
  const rsi = ta.rsi;
  const rsiState = rsi === null ? null
    : rsi < 30 ? { text: "저평가 구간", color: "var(--primary)" }
    : rsi > 70 ? { text: "고평가 구간", color: "var(--red)" }
    : { text: "보통", color: "var(--green)" };
  const cross = CROSS_LABEL[ta.cross_5_20];
  const hist = ta.macd_histogram;
  const macdState = hist === null ? null
    : hist > 0 ? { text: "매수 우세", color: "var(--red)" }
    : { text: "매도 우세", color: "var(--primary)" };

  return (
    <>
      {/* ── 한눈에 보기 ── */}
      <div style={{ background: "var(--surface)", borderRadius: 20, padding: "16px 18px", boxShadow: "var(--shadow)" }}>
        <div style={{ fontSize: 12, color: "var(--label3)", fontWeight: 600, marginBottom: 4 }}>한눈에 보기</div>
        <div style={{ borderTop: "0.5px solid var(--sep)" }}>
          <SignalRow
            title="과열도"
            status={rsiState?.text ?? "—"}
            value={rsi !== null ? `${rsi.toFixed(0)} / 100` : undefined}
            color={rsiState?.color ?? "var(--label3)"}
          />
          <div style={{ height: "0.5px", background: "var(--sep)" }} />
          <SignalRow
            title="추세"
            status={cross.text}
            value={ta.ma5 && ta.ma20 ? (cp > ta.ma20 ? "상승장" : "하락장") : undefined}
            color={cross.color}
          />
          <div style={{ height: "0.5px", background: "var(--sep)" }} />
          <SignalRow
            title="매수·매도"
            status={macdState?.text ?? "—"}
            color={macdState?.color ?? "var(--label3)"}
          />
        </div>

        {/* 1년 위치 */}
        <div style={{ marginTop: 14, paddingTop: 12, borderTop: "0.5px solid var(--sep)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: 12, color: "var(--label3)", fontWeight: 500 }}>
              1년 가격 범위 내 위치
            </span>
            <span style={{ fontSize: 12, fontWeight: 700, color: isFinite(ta.pos_in_52w_range) ? (ta.pos_in_52w_range > 70 ? "var(--red)" : ta.pos_in_52w_range < 30 ? "var(--primary)" : "var(--green)") : "var(--label3)" }}>
              {isFinite(ta.pos_in_52w_range) ? `${ta.pos_in_52w_range < 30 ? "바닥권" : ta.pos_in_52w_range > 70 ? "고점권" : "중간권"} · ${ta.pos_in_52w_range.toFixed(0)}%` : "—"}
            </span>
          </div>
          <RangeBar pct={ta.pos_in_52w_range} />
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
            <span style={{ fontSize: 11, color: "var(--label3)" }}>연저가 {fmt(ta.low_52w)}원</span>
            <span style={{ fontSize: 11, color: "var(--label3)" }}>연고가 {fmt(ta.high_52w)}원</span>
          </div>
        </div>
      </div>

      {/* ── 평균 주가 흐름 ── */}
      <div style={{ background: "var(--surface)", borderRadius: 20, padding: "16px 18px", boxShadow: "var(--shadow)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <span style={{ fontSize: 12, color: "var(--label3)", fontWeight: 600 }}>평균 주가 흐름</span>
          <span style={{ fontSize: 11, fontWeight: 700, color: cross.color, background: `${cross.color}14`, borderRadius: 6, padding: "2px 8px" }}>
            {cross.text}
          </span>
        </div>
        <div style={{ borderTop: "0.5px solid var(--sep)" }}>
          {([["5일 평균", ta.ma5], ["20일 평균", ta.ma20], ["60일 평균", ta.ma60]] as [string, number | null][])
            .filter(([, v]) => v !== null)
            .map(([label, val], i, arr) => {
              const v = val as number;
              const above = cp > v;
              const diffPct = (isFinite(v) && v > 0) ? ((cp - v) / v * 100) : null;
              return (
                <div key={label}>
                  {i > 0 && <div style={{ height: "0.5px", background: "var(--sep)" }} />}
                  <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 0" }}>
                    <div style={{ width: 8, height: 8, borderRadius: "50%", background: above ? "var(--red)" : "var(--primary)", flexShrink: 0 }} />
                    <span style={{ fontSize: 13, color: "var(--label3)", minWidth: 72, fontWeight: 500 }}>{label}</span>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "var(--label)", flex: 1 }}>{above ? "현재가 위" : "현재가 아래"}</span>
                    <span style={{ fontSize: 12, color: "var(--label3)" }}>{isFinite(v) ? `${fmt(v)}원` : "—"}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: above ? "var(--red)" : "var(--primary)" }}>
                      {diffPct !== null ? `${diffPct > 0 ? "+" : ""}${diffPct.toFixed(1)}%` : "—"}
                    </span>
                  </div>
                </div>
              );
            })}
        </div>
      </div>

      {/* ── 과열 지수 ── */}
      {rsi !== null && rsiState && (
        <div style={{ background: "var(--surface)", borderRadius: 20, padding: "16px 18px", boxShadow: "var(--shadow)" }}>
          <div style={{ fontSize: 12, color: "var(--label3)", fontWeight: 600, marginBottom: 4 }}>과열 지수</div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 0", borderTop: "0.5px solid var(--sep)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: rsiState.color, flexShrink: 0 }} />
              <span style={{ fontSize: 15, fontWeight: 700, color: rsiState.color }}>{rsiState.text}</span>
            </div>
            <span style={{ fontSize: 22, fontWeight: 800, color: rsiState.color, letterSpacing: "-0.04em" }}>{rsi.toFixed(0)}</span>
          </div>
          <div style={{ marginTop: 6 }}>
            <RangeBar pct={rsi} />
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 5 }}>
              <span style={{ fontSize: 10, color: "var(--primary)", fontWeight: 600 }}>저평가 30</span>
              <span style={{ fontSize: 10, color: "var(--label3)" }}>중립 50</span>
              <span style={{ fontSize: 10, color: "var(--red)", fontWeight: 600 }}>고평가 70</span>
            </div>
          </div>
        </div>
      )}

      {/* ── 상승·하락 압력 ── */}
      {ta.macd !== null && macdState && (
        <div style={{ background: "var(--surface)", borderRadius: 20, padding: "16px 18px", boxShadow: "var(--shadow)" }}>
          <div style={{ fontSize: 12, color: "var(--label3)", fontWeight: 600, marginBottom: 4 }}>상승·하락 압력</div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 0", borderTop: "0.5px solid var(--sep)", marginBottom: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: macdState.color, flexShrink: 0 }} />
              <span style={{ fontSize: 15, fontWeight: 700, color: macdState.color }}>{macdState.text}</span>
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div style={{ background: "var(--bg)", borderRadius: 10, padding: "10px 12px" }}>
              <div style={{ fontSize: 11, color: "var(--label3)", marginBottom: 3 }}>추세선</div>
              <div style={{ fontSize: 15, fontWeight: 700 }}>{isFinite(ta.macd) ? `${ta.macd > 0 ? "+" : ""}${ta.macd.toFixed(1)}` : "—"}</div>
            </div>
            <div style={{ background: "var(--bg)", borderRadius: 10, padding: "10px 12px" }}>
              <div style={{ fontSize: 11, color: "var(--label3)", marginBottom: 3 }}>압력 강도</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: macdState.color }}>
                {hist !== null && hist > 0 ? "+" : ""}{hist?.toFixed(1)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── 가격 변동 구간 ── */}
      {ta.bb_upper && ta.bb_mid && ta.bb_lower && (
        <div style={{ background: "var(--surface)", borderRadius: 20, padding: "16px 18px", boxShadow: "var(--shadow)" }}>
          <div style={{ fontSize: 12, color: "var(--label3)", fontWeight: 600, marginBottom: 4 }}>가격 변동 구간</div>
          {ta.bb_position !== null && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 0", borderTop: "0.5px solid var(--sep)", marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: ta.bb_position > 70 ? "var(--red)" : ta.bb_position < 30 ? "var(--primary)" : "var(--green)", flexShrink: 0 }} />
                <span style={{ fontSize: 14, fontWeight: 700, color: ta.bb_position > 70 ? "var(--red)" : ta.bb_position < 30 ? "var(--primary)" : "var(--green)" }}>
                  {ta.bb_position > 70 ? "고평가 구간에 가까움" : ta.bb_position < 30 ? "저평가 구간에 가까움" : "중간 구간"}
                </span>
              </div>
              <span style={{ fontSize: 12, color: "var(--label3)" }}>{isFinite(ta.bb_position) ? `${ta.bb_position.toFixed(0)}%` : "—"}</span>
            </div>
          )}
          <RangeBar pct={ta.bb_position ?? 50} />
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
            <div style={{ textAlign: "left" }}>
              <div style={{ fontSize: 10, color: "var(--primary)", fontWeight: 700 }}>하단 (저평가)</div>
              <div style={{ fontSize: 12, fontWeight: 700, marginTop: 2 }}>{fmt(ta.bb_lower)}</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 10, color: "var(--label3)", fontWeight: 600 }}>중간선</div>
              <div style={{ fontSize: 12, fontWeight: 700, marginTop: 2 }}>{fmt(ta.bb_mid)}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 10, color: "var(--red)", fontWeight: 700 }}>상단 (고평가)</div>
              <div style={{ fontSize: 12, fontWeight: 700, marginTop: 2 }}>{fmt(ta.bb_upper)}</div>
            </div>
          </div>
        </div>
      )}

      {/* ── 주요 가격대 ── */}
      {(ta.support || ta.resistance) && (
        <div style={{ background: "var(--surface)", borderRadius: 20, padding: "16px 18px", boxShadow: "var(--shadow)" }}>
          <div style={{ fontSize: 12, color: "var(--label3)", fontWeight: 600, marginBottom: 4 }}>주요 가격대</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, borderTop: "0.5px solid var(--sep)", paddingTop: 12 }}>
            <div style={{ background: "rgba(0,122,255,0.06)", borderRadius: 12, padding: "12px 14px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                <div style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--primary)" }} />
                <span style={{ fontSize: 12, color: "var(--primary)", fontWeight: 700 }}>바닥 (지지선)</span>
              </div>
              <div style={{ fontSize: 18, fontWeight: 800 }}>{ta.support ? fmt(ta.support) : "—"}</div>
              {ta.support && cp && (
                <div style={{ fontSize: 11, color: "var(--label3)", marginTop: 3 }}>
                  현재 대비 {((ta.support - cp) / cp * 100).toFixed(1)}%
                </div>
              )}
            </div>
            <div style={{ background: "rgba(255,59,48,0.06)", borderRadius: 12, padding: "12px 14px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                <div style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--red)" }} />
                <span style={{ fontSize: 12, color: "var(--red)", fontWeight: 700 }}>천장 (저항선)</span>
              </div>
              <div style={{ fontSize: 18, fontWeight: 800 }}>{ta.resistance ? fmt(ta.resistance) : "—"}</div>
              {ta.resistance && cp && (
                <div style={{ fontSize: 11, color: "var(--label3)", marginTop: 3 }}>
                  현재 대비 {((ta.resistance - cp) / cp * 100).toFixed(1)}%
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

const COMMENTARY_SENTIMENT = {
  bullish:  { label: "강세", color: "var(--red)",    bg: "rgba(255,59,48,0.06)",    dot: "#FF3B30" },
  bearish:  { label: "약세", color: "var(--primary)", bg: "rgba(0,122,255,0.06)",   dot: "#007AFF" },
  neutral:  { label: "중립", color: "var(--label3)",  bg: "var(--surface2)",         dot: "#AEAEB2" },
};

function CommentaryCard({
  sections, fallback, loading, onRefresh,
}: {
  sections: CommentarySections | null;
  fallback: string | null;
  loading: boolean;
  onRefresh: () => void;
}) {
  const sentiment = sections?.sentiment ?? "neutral";
  const cfg = COMMENTARY_SENTIMENT[sentiment] ?? COMMENTARY_SENTIMENT.neutral;

  return (
    <div style={{ background: "var(--surface)", borderRadius: 20, overflow: "hidden", boxShadow: "var(--shadow)" }}>
      <div style={{
        padding: "14px 20px 12px",
        background: cfg.bg,
        borderBottom: "0.5px solid var(--sep)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 7, height: 7, borderRadius: "50%", background: cfg.dot, flexShrink: 0 }} />
          <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: "-0.022em" }}>AI 시황 해설</span>
          {sections && (
            <span style={{
              fontSize: 10, fontWeight: 700, color: cfg.color,
              background: `${cfg.dot}20`, borderRadius: 6, padding: "2px 7px",
              letterSpacing: "-0.01em",
            }}>
              {cfg.label}
            </span>
          )}
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          style={{
            fontSize: 12, color: "var(--primary)", fontWeight: 700,
            padding: "6px 12px", background: "rgba(0,122,255,0.10)", borderRadius: 100,
            letterSpacing: "-0.01em",
          }}
        >
          {loading ? "…" : "새로고침"}
        </button>
      </div>

      <div style={{ padding: "14px 20px 16px" }}>
        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[100, 92, 76, 60].map((w, i) => (
              <Skeleton key={i} height={14} width={`${w}%`} />
            ))}
          </div>
        ) : sections ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <p style={{ fontSize: 15, fontWeight: 700, color: "var(--label)", margin: 0, letterSpacing: "-0.022em", lineHeight: 1.45 }}>
              {sections.headline}
            </p>
            <p style={{ fontSize: 14, color: "var(--label)", lineHeight: 1.65, margin: 0, letterSpacing: "-0.015em" }}>
              {sections.trend}
            </p>
            {sections.signal && (
              <div style={{
                background: "rgba(0,122,255,0.06)", borderRadius: 12, padding: "10px 13px",
                borderLeft: "3px solid var(--primary)",
                display: "flex", flexDirection: "column", gap: 4,
              }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: "var(--primary)" }}>기술 신호</div>
                <p style={{ fontSize: 13, color: "var(--primary)", lineHeight: 1.65, margin: 0, letterSpacing: "-0.01em" }}>{sections.signal}</p>
              </div>
            )}
            {sections.note && (
              <div style={{ display: "flex", gap: 8, borderTop: "0.5px solid var(--sep)", paddingTop: 10 }}>
                <div style={{
                  fontSize: 10, fontWeight: 700, color: "white",
                  background: "var(--orange)", borderRadius: 5,
                  padding: "2px 7px", flexShrink: 0, alignSelf: "flex-start", marginTop: 2,
                }}>포인트</div>
                <p style={{ fontSize: 13, color: "var(--label2)", lineHeight: 1.65, margin: 0, letterSpacing: "-0.015em" }}>{sections.note}</p>
              </div>
            )}
          </div>
        ) : fallback ? (
          <p style={{ fontSize: 13, color: "var(--label)", lineHeight: 1.8, margin: 0 }}>{fallback}</p>
        ) : (
          <p style={{ fontSize: 13, color: "var(--label2)", margin: 0 }}>AI 해설을 불러오지 못했습니다.</p>
        )}
      </div>
    </div>
  );
}


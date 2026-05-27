"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchPortfolioOneliner,
  fetchPortfolioMovers,
  fetchPortfolioSnapshots,
  fetchMarketIndices,
  listPortfolio,
  fetchStockPrice,
  fetchPortfolioAlerts,
} from "../lib/api";
import type { MarketIndex, PortfolioItem, PortfolioMover, PortfolioOneliner, PortfolioSnapshot, StockPrice } from "../lib/types";

type Props = {
  onNavigate?: (panel: "portfolio" | "watchlist" | "chat" | "screener" | "alerts") => void;
  onSelectStock?: (item: PortfolioItem) => void;
};

function fmt(n: number) { return n.toLocaleString("ko-KR"); }
function fmtShort(n: number) {
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${(n / 1e8).toFixed(1)}억`;
  return `${Math.round(n / 1e4).toLocaleString("ko-KR")}만`;
}
function pctColor(pct: number) { return pct >= 0 ? "var(--red)" : "var(--primary)"; }
function pctSign(pct: number) { return `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`; }

export function HomeCard({ onNavigate, onSelectStock }: Props) {
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [prices, setPrices] = useState<Record<string, StockPrice>>({});
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([]);
  const [oneliner, setOneliner] = useState<PortfolioOneliner | null>(null);
  const [movers, setMovers] = useState<PortfolioMover[]>([]);
  const [indices, setIndices] = useState<Record<string, MarketIndex>>({});
  const [alertCount, setAlertCount] = useState(0);

  // 포트폴리오 + 시세
  useEffect(() => {
    let cancelled = false;
    listPortfolio().then((list) => {
      if (cancelled) return;
      setItems(list);
      list.forEach((it) => {
        fetchStockPrice(it.stock_code).then((p) => {
          if (cancelled) return;
          setPrices((prev) => ({ ...prev, [it.stock_code]: p }));
        }).catch(() => {});
      });
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // 7일 추이 (snapshots)
  useEffect(() => {
    fetchPortfolioSnapshots(14).then((d) => setSnapshots(d.snapshots ?? [])).catch(() => {});
  }, []);

  // AI 한 줄
  useEffect(() => {
    fetchPortfolioOneliner().then(setOneliner).catch(() => {});
  }, []);

  // 무버
  useEffect(() => {
    fetchPortfolioMovers().then(setMovers).catch(() => {});
  }, []);

  // 시장 지수
  useEffect(() => {
    fetchMarketIndices().then((d) => setIndices(d.indices ?? {})).catch(() => {});
  }, []);

  // 알림 카운트
  useEffect(() => {
    fetchPortfolioAlerts().then((m) => {
      const total = Object.values(m).reduce((s: number, n) => s + (n as number), 0);
      setAlertCount(total);
    }).catch(() => {});
  }, []);

  // 손익 집계
  const summary = useMemo(() => {
    const totalInvested = items.reduce((s, i) => s + i.buy_price * i.quantity, 0);
    const totalCurrent = items.reduce((s, i) => {
      const p = prices[i.stock_code];
      return s + (p ? p.current_price * i.quantity : i.buy_price * i.quantity);
    }, 0);
    const pnl = totalCurrent - totalInvested;
    const pnlPct = totalInvested > 0 ? (pnl / totalInvested) * 100 : 0;
    return { totalInvested, totalCurrent, pnl, pnlPct };
  }, [items, prices]);

  const isProfit = summary.pnlPct >= 0;
  const tone = isProfit ? "up" : "down";

  // 7일 sparkline (snapshots 기반)
  const sparkPoints = useMemo(() => {
    return snapshots.slice(-7).map((s) => s.total_value);
  }, [snapshots]);

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflowY: "auto", padding: 14, gap: 10 }}>

      {/* 1. Hero P&L with sparkline + sentiment tint */}
      <HeroPnL tone={tone} pnlPct={summary.pnlPct} totalValue={summary.totalCurrent} sparkPoints={sparkPoints} onClick={() => onNavigate?.("portfolio")} />

      {/* 2. AI 한 줄 브리핑 */}
      <AIBriefingWidget oneliner={oneliner} onClick={() => onNavigate?.("chat")} />

      {/* 3. 오늘 움직임 */}
      <MoversWidget movers={movers} onSelect={(m) => onSelectStock?.({ stock_code: m.stock_code, corp_name: m.corp_name, buy_price: 0, quantity: 0 })} onAll={() => onNavigate?.("portfolio")} />

      {/* 4. 시장 현황 */}
      <MarketWidget indices={indices} />

      {/* 5. 하단 strip — 알림 + 빠른 액션 */}
      <FooterStrip alertCount={alertCount} onAlert={() => onNavigate?.("alerts")} onNav={onNavigate} />

    </div>
  );
}

// ─── Hero P&L ────────────────────────────────────────────────────────────────

function HeroPnL({ tone, pnlPct, totalValue, sparkPoints, onClick }: {
  tone: "up" | "down";
  pnlPct: number;
  totalValue: number;
  sparkPoints: number[];
  onClick?: () => void;
}) {
  const color = tone === "up" ? "var(--red)" : "var(--primary)";
  const bg = tone === "up"
    ? "linear-gradient(135deg, rgba(255,59,48,0.10) 0%, rgba(255,59,48,0.02) 100%)"
    : "linear-gradient(135deg, rgba(0,122,255,0.10) 0%, rgba(0,122,255,0.02) 100%)";
  const border = tone === "up" ? "rgba(255,59,48,0.25)" : "rgba(0,122,255,0.25)";

  // sparkline
  const validPoints = sparkPoints.filter((v) => isFinite(v) && v > 0);
  const hasChart = validPoints.length >= 2;
  const min = hasChart ? Math.min(...validPoints) : 0;
  const max = hasChart ? Math.max(...validPoints) : 1;
  const range = max - min || 1;
  const W = 320, H = 80;
  const polyPoints = validPoints.map((v, i) => {
    const x = (i / (validPoints.length - 1)) * W;
    const y = H - ((v - min) / range) * (H - 10) - 5;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const lastY = hasChart
    ? H - ((validPoints[validPoints.length - 1] - min) / range) * (H - 10) - 5
    : H / 2;

  const cumPnl = validPoints.length >= 2
    ? ((validPoints[validPoints.length - 1] - validPoints[0]) / validPoints[0]) * 100
    : 0;

  return (
    <div
      onClick={onClick}
      style={{
        padding: 16,
        borderRadius: 16,
        background: bg,
        border: `0.5px solid ${border}`,
        cursor: onClick ? "pointer" : undefined,
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontSize: 11, color: "var(--label2)", fontWeight: 700, letterSpacing: "-0.01em" }}>
          7일 평가손익 추이
        </span>
        <span style={{ fontSize: 11, color: "var(--primary)", fontWeight: 700 }}>상세 →</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 4, fontVariantNumeric: "tabular-nums" }}>
        <span style={{ fontSize: 28, fontWeight: 800, letterSpacing: "-0.04em", color, lineHeight: 1 }}>
          {pnlPct > 0 ? "+" : ""}{pnlPct.toFixed(2)}%
        </span>
        <span style={{ fontSize: 12, color: "var(--label2)", fontWeight: 600 }}>
          평가 {fmtShort(totalValue)}원
        </span>
      </div>
      <div style={{ fontSize: 11, color: "var(--label3)", fontWeight: 600, marginBottom: 12, fontVariantNumeric: "tabular-nums" }}>
        7일 누적 {cumPnl > 0 ? "+" : ""}{cumPnl.toFixed(1)}%
      </div>
      {hasChart ? (
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: 80 }} preserveAspectRatio="none">
          <defs>
            <linearGradient id="homeGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={tone === "up" ? "rgba(255,59,48,0.30)" : "rgba(0,122,255,0.30)"} />
              <stop offset="100%" stopColor={tone === "up" ? "rgba(255,59,48,0)" : "rgba(0,122,255,0)"} />
            </linearGradient>
          </defs>
          <polygon fill="url(#homeGrad)" points={`${polyPoints} ${W},${H} 0,${H}`} />
          <polyline fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" points={polyPoints} />
          <circle cx={W} cy={lastY} r="3" fill={color} />
        </svg>
      ) : (
        <div style={{ height: 80, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--label3)", fontSize: 11 }}>
          데이터를 모으는 중이에요
        </div>
      )}
    </div>
  );
}

// ─── AI 한 줄 ───────────────────────────────────────────────────────────────

function AIBriefingWidget({ oneliner, onClick }: { oneliner: PortfolioOneliner | null; onClick?: () => void }) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: 14,
        borderRadius: 16,
        background: "linear-gradient(135deg, rgba(0,122,255,0.06), rgba(88,86,214,0.04))",
        border: "0.5px solid rgba(0,122,255,0.20)",
        cursor: onClick ? "pointer" : undefined,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontSize: 11, color: "var(--primary)", fontWeight: 700, letterSpacing: "-0.01em" }}>
          ✨ AI 브리핑
        </span>
        <span style={{ fontSize: 11, color: "var(--primary)", fontWeight: 700 }}>전체 →</span>
      </div>
      <p style={{
        fontSize: 14, fontWeight: 700, letterSpacing: "-0.022em",
        lineHeight: 1.5, color: "var(--label)", margin: 0,
      }}>
        {oneliner?.headline ?? "AI가 브리핑을 준비하고 있어요…"}
      </p>
      {oneliner?.generated_at && (
        <div style={{ fontSize: 10, color: "var(--label3)", marginTop: 6, fontVariantNumeric: "tabular-nums" }}>
          {oneliner.generated_at}
        </div>
      )}
    </div>
  );
}

// ─── 오늘 움직임 ─────────────────────────────────────────────────────────────

function MoversWidget({ movers, onSelect, onAll }: {
  movers: PortfolioMover[];
  onSelect: (m: PortfolioMover) => void;
  onAll: () => void;
}) {
  return (
    <div style={{
      padding: 14,
      borderRadius: 16,
      background: "var(--surface)",
      border: "0.5px solid var(--sep)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontSize: 11, color: "var(--label2)", fontWeight: 700, letterSpacing: "-0.01em" }}>
          오늘 움직임
        </span>
        <button
          onClick={onAll}
          style={{ fontSize: 11, color: "var(--primary)", fontWeight: 700, padding: 0 }}
        >
          전체 →
        </button>
      </div>
      {movers.length === 0 ? (
        <div style={{ padding: "12px 0", textAlign: "center", color: "var(--label3)", fontSize: 12 }}>
          아직 데이터가 없어요
        </div>
      ) : (
        movers.map((m) => (
          <MoverRow key={m.stock_code} mover={m} onClick={() => onSelect(m)} />
        ))
      )}
    </div>
  );
}

function MoverRow({ mover, onClick }: { mover: PortfolioMover; onClick: () => void }) {
  const isUp = mover.change_pct >= 0;
  const color = isUp ? "var(--red)" : "var(--primary)";
  const bgTint = isUp ? "rgba(255,59,48,0.05)" : "rgba(0,122,255,0.05)";

  const points = mover.sparkline.filter((v) => isFinite(v));
  const hasSpark = points.length >= 2;
  const min = hasSpark ? Math.min(...points) : 0;
  const max = hasSpark ? Math.max(...points) : 1;
  const range = max - min || 1;
  const W = 32, H = 18;
  const polyPoints = hasSpark ? points.map((v, i) => {
    const x = (i / (points.length - 1)) * W;
    const y = H - ((v - min) / range) * (H - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ") : "";

  return (
    <div
      onClick={onClick}
      style={{
        display: "grid",
        gridTemplateColumns: "1fr auto",
        alignItems: "center",
        gap: 10,
        padding: "8px 10px",
        borderRadius: 8,
        margin: "0 -4px",
        marginTop: 4,
        background: bgTint,
        cursor: "pointer",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
        {hasSpark && (
          <svg viewBox={`0 0 ${W} ${H}`} style={{ width: 32, height: 18, flexShrink: 0 }}>
            <polyline fill="none" stroke={color} strokeWidth="1.4" points={polyPoints} />
          </svg>
        )}
        <span style={{
          fontSize: 13, fontWeight: 700, letterSpacing: "-0.02em",
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        }}>
          {mover.corp_name}
        </span>
      </div>
      <span style={{
        fontSize: 13, fontWeight: 800, letterSpacing: "-0.025em",
        color, fontVariantNumeric: "tabular-nums",
      }}>
        {mover.change_pct > 0 ? "+" : ""}{mover.change_pct.toFixed(2)}%
      </span>
    </div>
  );
}

// ─── 시장 현황 ────────────────────────────────────────────────────────────────

function MarketWidget({ indices }: { indices: Record<string, MarketIndex> }) {
  const list = Object.values(indices);
  return (
    <div style={{
      padding: 14,
      borderRadius: 16,
      background: "var(--surface)",
      border: "0.5px solid var(--sep)",
    }}>
      <div style={{ fontSize: 11, color: "var(--label2)", fontWeight: 700, letterSpacing: "-0.01em", marginBottom: 8 }}>
        시장 현황
      </div>
      {list.length === 0 ? (
        <div style={{ padding: "8px 0", textAlign: "center", color: "var(--label3)", fontSize: 11 }}>
          데이터를 불러오는 중이에요
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(list.length, 3)}, 1fr)`, gap: 6 }}>
          {list.slice(0, 3).map((idx) => {
            const up = idx.change_pct >= 0;
            const color = up ? "var(--red)" : "var(--primary)";
            const bg = up ? "rgba(255,59,48,0.05)" : "rgba(0,122,255,0.05)";
            const border = up ? "rgba(255,59,48,0.18)" : "rgba(0,122,255,0.18)";
            return (
              <div key={idx.name} style={{
                padding: "8px 10px",
                borderRadius: 10,
                background: bg,
                border: `0.5px solid ${border}`,
                display: "flex", flexDirection: "column", gap: 3,
              }}>
                <span style={{ fontSize: 10, color: "var(--label2)", fontWeight: 700 }}>{idx.name}</span>
                <span style={{ fontSize: 13, fontWeight: 800, letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums" }}>
                  {idx.value.toLocaleString("ko-KR")}
                </span>
                <span style={{ fontSize: 10, fontWeight: 700, color, fontVariantNumeric: "tabular-nums" }}>
                  {up ? "+" : ""}{idx.change_pct.toFixed(2)}%
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── 하단 strip — 알림 + 빠른 액션 ──────────────────────────────────────────

function FooterStrip({ alertCount, onAlert, onNav }: {
  alertCount: number;
  onAlert: () => void;
  onNav?: (panel: "portfolio" | "watchlist" | "chat" | "screener" | "alerts") => void;
}) {
  return (
    <div style={{ display: "flex", gap: 6 }}>
      <FooterButton
        icon={
          <svg viewBox="0 0 24 24" fill="none" stroke="var(--orange)" strokeWidth="2" strokeLinecap="round">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
          </svg>
        }
        label="알림"
        onClick={onAlert}
        badge={alertCount > 0 ? (alertCount > 9 ? "9+" : String(alertCount)) : undefined}
      />
      <FooterButton
        icon={
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <rect x="2" y="3" width="20" height="14" rx="2"/>
          </svg>
        }
        label="포트"
        onClick={() => onNav?.("portfolio")}
      />
      <FooterButton
        icon={
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
        }
        label="AI"
        onClick={() => onNav?.("chat")}
      />
      <FooterButton
        icon={
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
        }
        label="스크리너"
        onClick={() => onNav?.("screener")}
      />
    </div>
  );
}

function FooterButton({ icon, label, onClick, badge }: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  badge?: string;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        flex: 1,
        background: "var(--surface)",
        border: "0.5px solid var(--sep)",
        borderRadius: 12,
        padding: "11px 6px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 3,
        cursor: "pointer",
        position: "relative",
        color: "var(--primary)",
      }}
    >
      <div style={{ width: 18, height: 18 }}>{icon}</div>
      <span style={{ fontSize: 10, fontWeight: 700, color: "var(--label)", letterSpacing: "-0.01em" }}>
        {label}
      </span>
      {badge && (
        <span style={{
          position: "absolute", top: 6, right: 6,
          background: "var(--red)", color: "white",
          fontSize: 9, fontWeight: 800,
          padding: "1px 5px", borderRadius: 100,
          fontVariantNumeric: "tabular-nums",
        }}>
          {badge}
        </span>
      )}
    </button>
  );
}

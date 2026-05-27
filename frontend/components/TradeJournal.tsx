"use client";
import { useEffect, useMemo, useState } from "react";
import type { PortfolioItem, PortfolioSnapshot, Trade, TradeDiagnose, TradeSummaryItem } from "../lib/types";
import { fetchPortfolioSnapshots, fetchTradeDiagnose, fetchTrades, fetchTradeSummary } from "../lib/api";
import TradeDetailModal from "./TradeDetailModal";

type GraphMode = "value" | "pnl";
type Period = 30 | 90 | 180 | 365;

interface Props {
  portfolio: PortfolioItem[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatWon(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}백만`;
  if (Math.abs(n) >= 10_000) return `${(n / 10_000).toFixed(0)}만`;
  return `${n.toLocaleString()}`;
}

function pnlColor(n: number) {
  return n > 0 ? "var(--red)" : n < 0 ? "var(--primary)" : "var(--label2)";
}

const CORP_PALETTE = ["#007AFF", "#FF3B30", "#34C759", "#FF9500", "#AF52DE", "#5856D6", "#00C7BE", "#FF2D55"];

function corpColor(code: string): string {
  let h = 0;
  for (let i = 0; i < code.length; i++) h = (h * 31 + code.charCodeAt(i)) & 0x7fffffff;
  return CORP_PALETTE[h % CORP_PALETTE.length];
}

// ─── SVG Line Chart ──────────────────────────────────────────────────────────

interface LineChartProps {
  data: { x: string; y: number }[];
  color: string;   // hex color only
  gradId: string;
  height?: number;
}

function LineChart({ data, color, gradId, height = 120 }: LineChartProps) {
  if (data.length < 2) return null;
  const W = 600;
  const H = height;
  const PAD = { top: 8, bottom: 8, left: 0, right: 0 };
  const ys = data.map((d) => d.y);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const rangeY = maxY - minY || 1;

  const toX = (i: number) => PAD.left + (i / (data.length - 1)) * (W - PAD.left - PAD.right);
  const toY = (y: number) => PAD.top + (1 - (y - minY) / rangeY) * (H - PAD.top - PAD.bottom);

  const pts = data.map((d, i) => `${toX(i).toFixed(1)},${toY(d.y).toFixed(1)}`).join(" ");

  const areaPath =
    `M ${toX(0).toFixed(1)},${toY(data[0].y).toFixed(1)} ` +
    data.slice(1).map((d, i) => `L ${toX(i + 1).toFixed(1)},${toY(d.y).toFixed(1)}`).join(" ") +
    ` L ${toX(data.length - 1).toFixed(1)},${H} L ${toX(0).toFixed(1)},${H} Z`;

  const labelIndices = [0, Math.floor(data.length / 3), Math.floor((2 * data.length) / 3), data.length - 1];
  const uniqueLabels = [...new Set(labelIndices)];

  return (
    <svg viewBox={`0 0 ${W} ${H + 20}`} style={{ width: "100%", display: "block" }}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" style={{ stopColor: color, stopOpacity: 0.28 }} />
          <stop offset="100%" style={{ stopColor: color, stopOpacity: 0.02 }} />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradId})`} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      {uniqueLabels.map((i) => (
        <text key={i} x={toX(i)} y={H + 16} textAnchor="middle" fontSize="10" fill="#AEAEB2">
          {data[i].x.slice(5)}
        </text>
      ))}
    </svg>
  );
}

// ─── Trade Row ───────────────────────────────────────────────────────────────

const BADGE: Record<string, { label: string; bg: string; color: string }> = {
  buy:  { label: "매수", bg: "var(--green)",   color: "#fff" },
  sell: { label: "매도", bg: "var(--red)",     color: "#fff" },
  edit: { label: "수정", bg: "var(--primary)", color: "#fff" },
};

function TradeRow({ trade, onClick }: { trade: Trade; onClick: () => void }) {
  const b = BADGE[trade.trade_type];
  const dt = trade.created_at;
  const mmdd = dt.slice(5, 10).replace("-", "/");
  const time = dt.slice(11, 16);
  const ac = corpColor(trade.stock_code);

  return (
    <button
      onClick={onClick}
      style={{
        display: "flex", alignItems: "center", gap: 10,
        width: "100%", background: "none", border: "none", cursor: "pointer",
        padding: "11px 0", borderBottom: "0.5px solid var(--sep)",
        textAlign: "left",
      }}
    >
      {/* 아바타 */}
      <div style={{
        width: 36, height: 36, borderRadius: 10, flexShrink: 0,
        background: `${ac}1A`,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 14, fontWeight: 800, color: ac,
      }}>
        {trade.corp_name.slice(0, 1)}
      </div>

      {/* 종목명 + 서브정보 */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
          <span style={{
            flexShrink: 0, fontSize: 10, fontWeight: 700,
            padding: "2px 6px", borderRadius: 6,
            background: b.bg, color: b.color,
          }}>{b.label}</span>
          <span style={{ fontSize: 14, fontWeight: 700, letterSpacing: "-0.022em", color: "var(--label)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {trade.corp_name}
          </span>
        </div>
        <div style={{ fontSize: 11, color: "var(--label2)", fontVariantNumeric: "tabular-nums" }}>
          {trade.quantity.toLocaleString()}주 · {trade.price.toLocaleString()}원
          <span style={{ marginLeft: 8, color: "var(--label3)" }}>{mmdd} {time}</span>
        </div>
      </div>

      {/* 총액 */}
      <div style={{ flexShrink: 0, textAlign: "right" }}>
        <div style={{ fontSize: 13, color: "var(--label)", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
          {(trade.price * trade.quantity).toLocaleString()}원
        </div>
      </div>
    </button>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function TradeJournal({ portfolio }: Props) {
  const [graphMode, setGraphMode] = useState<GraphMode>("value");
  const [period, setPeriod] = useState<Period>(90);
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [summary, setSummary] = useState<TradeSummaryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Trade | null>(null);
  const [diagnose, setDiagnose] = useState<TradeDiagnose | null>(null);
  const [diagnoseLoading, setDiagnoseLoading] = useState(false);

  const priceMap = useMemo(() => {
    const m: Record<string, number> = {};
    portfolio.forEach((p) => { m[p.stock_code] = p.buy_price; });
    return m;
  }, [portfolio]);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchPortfolioSnapshots(365),
      fetchTrades({ limit: 100 }),
      fetchTradeSummary(),
    ]).then(([snap, tradesRes, summRes]) => {
      setSnapshots(snap.snapshots);
      setTrades(tradesRes.trades);
      setTotal(tradesRes.total);
      setSummary(summRes.items);
    }).catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchTradeDiagnose().then(setDiagnose).catch(() => {});
  }, []);

  async function refreshDiagnose() {
    setDiagnoseLoading(true);
    try {
      const d = await fetchTradeDiagnose(true);
      setDiagnose(d);
    } finally {
      setDiagnoseLoading(false);
    }
  }

  const filteredSnaps = useMemo(() => {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - period);
    return snapshots.filter((s) => new Date(s.snapshot_date) >= cutoff);
  }, [snapshots, period]);

  const pnlChartData = useMemo(() => {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - period);
    const filtered = summary.filter((s) => new Date(s.date) >= cutoff);
    let cum = 0;
    return filtered.map((s) => {
      cum += s.realized_pnl;
      return { x: s.date, y: cum };
    });
  }, [summary, period]);

  const valueChartData = useMemo(
    () => filteredSnaps.map((s) => ({ x: s.snapshot_date, y: s.total_value })),
    [filteredSnaps],
  );

  const currentChartData = graphMode === "value" ? valueChartData : pnlChartData;

  const totalRealized = useMemo(() => summary.reduce((a, s) => a + s.realized_pnl, 0), [summary]);
  const latestSnap = snapshots[snapshots.length - 1];
  const valueGrowthPct = useMemo(() => {
    if (filteredSnaps.length < 2) return null;
    const first = filteredSnaps[0].total_value;
    const last = filteredSnaps[filteredSnaps.length - 1].total_value;
    return ((last - first) / first) * 100;
  }, [filteredSnaps]);

  if (loading) {
    return (
      <div style={{ padding: "24px 0", textAlign: "center", color: "var(--label2)", fontSize: 14 }}>
        잠시만요…
      </div>
    );
  }

  const PERIODS: { label: string; value: Period }[] = [
    { label: "1M", value: 30 },
    { label: "3M", value: 90 },
    { label: "6M", value: 180 },
    { label: "1Y", value: 365 },
  ];

  // 차트 색상 — SVG는 CSS 변수 미지원이므로 hex 직접 사용
  const chartColor =
    graphMode === "pnl"
      ? (totalRealized >= 0 ? "#FF3B30" : "#1E90FF")
      : "#007AFF";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Graph Section */}
      <div style={{ background: "var(--surface)", borderRadius: 16, padding: "16px", boxShadow: "var(--shadow-sm)", border: "0.5px solid var(--sep)" }}>
        {/* Toggle + Period */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div style={{ display: "flex", gap: 4, background: "var(--bg)", borderRadius: 100, padding: 3 }}>
            {(["value", "pnl"] as GraphMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setGraphMode(m)}
                style={{
                  padding: "5px 14px", borderRadius: 100, border: "none", cursor: "pointer",
                  fontSize: 12, fontWeight: graphMode === m ? 700 : 600,
                  background: graphMode === m ? "var(--primary)" : "transparent",
                  color: graphMode === m ? "#fff" : "var(--label2)",
                  transition: "background 0.15s",
                  letterSpacing: "-0.01em",
                }}
              >
                {m === "value" ? "총 평가액" : "실현 손익"}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 4, background: "var(--bg)", borderRadius: 100, padding: 3 }}>
            {PERIODS.map(({ label, value }) => (
              <button
                key={value}
                onClick={() => setPeriod(value)}
                style={{
                  padding: "4px 10px", borderRadius: 100, border: "none", cursor: "pointer",
                  fontSize: 11, fontWeight: period === value ? 700 : 600,
                  background: period === value ? "var(--primary)" : "transparent",
                  color: period === value ? "#fff" : "var(--label2)",
                  letterSpacing: "-0.01em",
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Summary Stat */}
        {graphMode === "value" && latestSnap && (
          <div style={{ marginBottom: 10 }}>
            <span style={{
              fontSize: 22, fontWeight: 800, color: "var(--label)",
              letterSpacing: "-0.035em",
              fontVariantNumeric: "tabular-nums",
            }}>
              {latestSnap.total_value.toLocaleString()}원
            </span>
            {valueGrowthPct != null && (
              <span style={{
                fontSize: 13, fontWeight: 700, marginLeft: 8, color: pnlColor(valueGrowthPct),
                fontVariantNumeric: "tabular-nums",
              }}>
                {valueGrowthPct >= 0 ? "+" : ""}{valueGrowthPct.toFixed(2)}%
              </span>
            )}
          </div>
        )}
        {graphMode === "pnl" && (
          <div style={{ marginBottom: 10 }}>
            <span style={{
              fontSize: 22, fontWeight: 800, letterSpacing: "-0.035em",
              color: totalRealized === 0 ? "var(--label)" : pnlColor(totalRealized),
              fontVariantNumeric: "tabular-nums",
            }}>
              {totalRealized > 0 ? "+" : ""}{formatWon(totalRealized)}원
            </span>
            <span style={{ fontSize: 11, color: "var(--label2)", marginLeft: 8 }}>
              누적 실현 손익 · {summary.length}건
            </span>
          </div>
        )}

        {/* Chart */}
        {currentChartData.length >= 2 ? (
          <LineChart
            data={currentChartData}
            color={chartColor}
            gradId={`grad-${graphMode}`}
            height={110}
          />
        ) : (
          <div style={{
            height: 80, display: "flex", alignItems: "center", justifyContent: "center",
            color: "var(--label2)", fontSize: 13, textAlign: "center", lineHeight: 1.6,
          }}>
            {graphMode === "value"
              ? "데이터를 모으는 중이에요 · 장 마감 후 첫 기록이 저장됩니다"
              : summary.length === 0
                ? "아직 실현된 손익이 없어요"
                : "거래 2건 이상부터 차트가 그려져요"}
          </div>
        )}
      </div>

      {/* AI 매매 패턴 진단 */}
      {diagnose && (
        <DiagnoseCard diagnose={diagnose} onRefresh={refreshDiagnose} loading={diagnoseLoading} />
      )}

      {/* Trade List */}
      <div>
        <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: "-0.022em", color: "var(--label)", marginBottom: 10 }}>
          거래 이력 {total > 0 && <span style={{ color: "var(--label3)", fontWeight: 500, fontSize: 13 }}>({total}건)</span>}
        </div>
        {trades.length === 0 ? (
          <div style={{ padding: "20px 0", textAlign: "center", color: "var(--label2)", fontSize: 13 }}>
            아직 기록된 거래가 없어요
          </div>
        ) : (
          trades.map((t) => (
            <TradeRow key={t.id} trade={t} onClick={() => setSelected(t)} />
          ))
        )}
      </div>

      {/* Detail Modal */}
      {selected && (
        <TradeDetailModal
          trade={selected}
          currentPrice={priceMap[selected.stock_code]}
          onClose={() => setSelected(null)}
          onMemoSaved={(id, memo) => {
            setTrades((prev) => prev.map((t) => t.id === id ? { ...t, memo } : t));
          }}
          onDeleted={(id) => {
            setTrades((prev) => prev.filter((t) => t.id !== id));
            setTotal((prev) => Math.max(0, prev - 1));
            setSelected(null);
          }}
          onEdited={(updated) => {
            setTrades((prev) => prev.map((t) => t.id === updated.id ? updated : t));
            setSelected(updated);
          }}
        />
      )}
    </div>
  );
}

function DiagnoseCard({ diagnose, onRefresh, loading }: {
  diagnose: TradeDiagnose;
  onRefresh: () => void;
  loading: boolean;
}) {
  return (
    <div style={{
      background: "linear-gradient(135deg, rgba(0,122,255,0.06), rgba(88,86,214,0.04))",
      border: "0.5px solid rgba(0,122,255,0.20)",
      borderRadius: 16,
      padding: "14px 16px",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontSize: 11, color: "var(--primary)", fontWeight: 700, letterSpacing: "-0.01em" }}>
          ✨ AI 매매 패턴 진단
        </span>
        <button
          onClick={onRefresh}
          disabled={loading}
          style={{
            fontSize: 11, color: "var(--primary)", fontWeight: 700,
            padding: "5px 12px", background: "rgba(0,122,255,0.10)", borderRadius: 100,
            letterSpacing: "-0.01em",
          }}
        >
          {loading ? "분석 중…" : "다시 분석"}
        </button>
      </div>
      <p style={{
        fontSize: 14, fontWeight: 600, color: "var(--label)",
        lineHeight: 1.55, letterSpacing: "-0.015em", margin: "0 0 12px",
      }}>
        {diagnose.diagnosis}
      </p>
      {diagnose.patterns.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {diagnose.patterns.map((p, i) => {
            const color = p.tone === "positive" ? "var(--red)" : p.tone === "negative" ? "var(--primary)" : "var(--label3)";
            const bg = p.tone === "positive" ? "rgba(255,59,48,0.06)" : p.tone === "negative" ? "rgba(0,122,255,0.06)" : "var(--surface2)";
            return (
              <div key={i} style={{
                background: bg, borderRadius: 10, padding: "9px 12px",
                borderLeft: `3px solid ${color}`,
              }}>
                <div style={{ fontSize: 11, fontWeight: 800, color, letterSpacing: "-0.01em", marginBottom: 3 }}>
                  {p.label}
                </div>
                <div style={{ fontSize: 12, color: "var(--label2)", lineHeight: 1.5, letterSpacing: "-0.015em" }}>
                  {p.detail}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <div style={{ fontSize: 10, color: "var(--label3)", marginTop: 8, fontVariantNumeric: "tabular-nums" }}>
        매매 {diagnose.trade_count}건 분석 · {diagnose.generated_at}
      </div>
    </div>
  );
}

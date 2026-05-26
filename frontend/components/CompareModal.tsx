"use client";

import { useEffect, useRef, useState } from "react";

import { fetchCompare, searchStock } from "../lib/api";
import type { CompareResponse, CompareStock, SearchResult } from "../lib/types";

type Props = {
  initialCode?: string;
  initialName?: string;
  onClose: () => void;
};

type Slot = { code: string; name: string };
type MetricKey = keyof CompareStock["metrics"];

// ─── 포맷 헬퍼 ────────────────────────────────────────────────────────────────

function fmtNum(v: number | null): string {
  return v === null ? "–" : v.toFixed(1);
}
function fmtPct(v: number | null): string {
  if (v === null) return "–";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}
function fmtMarketCap(v: number | null): string {
  if (v === null) return "–";
  // market_cap 단위: 억원. 10000억 = 1조
  if (v >= 10000) return `${(v / 10000).toFixed(0)}조`;
  return `${Math.round(v).toLocaleString("ko-KR")}억`;
}
function fmtForeignNet(v: number | null): string {
  if (v === null) return "–";
  // foreign_net_buy 단위: 원. 1억원 = 1e8
  const billions = Math.round(Math.abs(v) / 1e8);
  return `${v >= 0 ? "+" : "–"}${billions.toLocaleString("ko-KR")}억`;
}
function fmtRatio(v: number | null): string {
  return v === null ? "–" : `${v.toFixed(1)}x`;
}

// ─── 더 좋은 값 판단 ──────────────────────────────────────────────────────────

function better(key: MetricKey, a: number | null, b: number | null): "A" | "B" | null {
  if (a === null || b === null) return null;
  const lowerBetter = key === "per" || key === "pbr";
  if (lowerBetter) return a < b ? "A" : b < a ? "B" : null;
  return a > b ? "A" : b > a ? "B" : null;
}

// ─── 지표 행 설정 ─────────────────────────────────────────────────────────────

const ROWS: { label: string; key: MetricKey; fmt: (v: number | null) => string }[] = [
  { label: "시가총액",      key: "market_cap",     fmt: fmtMarketCap  },
  { label: "PER",          key: "per",            fmt: fmtNum        },
  { label: "PBR",          key: "pbr",            fmt: fmtNum        },
  { label: "RSI",          key: "rsi",            fmt: fmtNum        },
  { label: "20일 모멘텀",   key: "momentum_20d",   fmt: fmtPct        },
  { label: "거래량 비율",   key: "volume_ratio",   fmt: fmtRatio      },
  { label: "외국인 순매수", key: "foreign_net_buy", fmt: fmtForeignNet },
];

// ─── 기간 선택 옵션 ───────────────────────────────────────────────────────────

const PERIODS: { key: "1m" | "3m" | "6m" | "1y"; label: string }[] = [
  { key: "1m", label: "1M" },
  { key: "3m", label: "3M" },
  { key: "6m", label: "6M" },
  { key: "1y", label: "1Y" },
];

// ─── 수익률 차트 ──────────────────────────────────────────────────────────────

function ReturnChart({ data }: { data: CompareResponse }) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const chartRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const s0 = data.stocks[0].price_series;
    const s1 = data.stocks[1].price_series;
    if (s0.length === 0 && s1.length === 0) {
      if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }
      return;
    }

    let mounted = true;

    async function init() {
      const { createChart, LineSeries } = await import("lightweight-charts");
      if (!mounted || !containerRef.current) return;
      if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }

      const chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: 140,
        layout: {
          background: { color: "transparent" },
          textColor: "#8E8E93",
          fontSize: 10,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'Pretendard Variable', sans-serif",
        },
        grid: {
          vertLines: { color: "rgba(60,60,67,0.06)" },
          horzLines: { color: "rgba(60,60,67,0.06)" },
        },
        rightPriceScale: {
          borderVisible: false,
          textColor: "#AEAEB2",
          scaleMargins: { top: 0.1, bottom: 0.1 },
        },
        timeScale: {
          borderVisible: false,
          tickMarkFormatter: (t: unknown) => {
            if (typeof t === "string") {
              const p = (t as string).split("-");
              return `${parseInt(p[1])}/${parseInt(p[2])}`;
            }
            return String(t);
          },
        },
        handleScroll: false,
        handleScale: false,
      });
      chartRef.current = chart;

      if (s0.length > 0) {
        const seriesA = chart.addSeries(LineSeries, {
          color: "#007AFF",
          lineWidth: 2 as const,
          priceLineVisible: false,
          lastValueVisible: true,
        });
        seriesA.setData(s0.map(p => ({ time: p.date, value: p.return_pct })));
      }
      if (s1.length > 0) {
        const seriesB = chart.addSeries(LineSeries, {
          color: "#FF9500",
          lineWidth: 2 as const,
          priceLineVisible: false,
          lastValueVisible: true,
        });
        seriesB.setData(s1.map(p => ({ time: p.date, value: p.return_pct })));
      }
      chart.timeScale().fitContent();
    }

    init();
    return () => {
      mounted = false;
      if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }
    };
  }, [data]);

  return <div ref={containerRef} style={{ width: "100%" }} />;
}

// ─── 종목 슬롯 카드 ───────────────────────────────────────────────────────────

function StockSlot({
  slot, color, label, isSearching, onOpen, onClose: onSlotClose,
  query, onQueryChange, results, searching, onSelect,
}: {
  slot: Slot | null;
  color: string;
  label: string;
  isSearching: boolean;
  onOpen: () => void;
  onClose: () => void;
  query: string;
  onQueryChange: (q: string) => void;
  results: SearchResult[];
  searching: boolean;
  onSelect: (r: SearchResult) => void;
}) {
  return (
    <div style={{ position: "relative" }}>
      <div
        onClick={isSearching ? undefined : onOpen}
        style={{
          border: `1.5px solid ${color}`,
          borderRadius: 12,
          padding: "10px 14px",
          cursor: isSearching ? "default" : "pointer",
          minHeight: 62,
        }}
      >
        <div style={{ fontSize: 10, fontWeight: 600, color, letterSpacing: "0.3px", marginBottom: 3 }}>
          {label}
        </div>
        {isSearching ? (
          <input
            autoFocus
            value={query}
            onChange={e => onQueryChange(e.target.value)}
            placeholder="종목명 검색..."
            style={{
              width: "100%",
              border: "none",
              outline: "none",
              fontSize: 13,
              fontWeight: 700,
              background: "transparent",
              color: "var(--label)",
              letterSpacing: "-0.3px",
            }}
          />
        ) : (
          <>
            <div style={{
              fontWeight: 700,
              fontSize: 14,
              letterSpacing: "-0.3px",
              color: slot ? "var(--label)" : "var(--label3)",
            }}>
              {slot ? slot.name : "종목 선택"}
            </div>
            {slot && (
              <div style={{ fontSize: 11, color: "var(--label2)", marginTop: 1, fontFamily: "monospace" }}>
                {slot.code}
              </div>
            )}
          </>
        )}
      </div>

      {/* 검색 드롭다운 */}
      {isSearching && (
        <div style={{
          position: "absolute",
          top: "calc(100% + 4px)",
          left: 0,
          right: 0,
          background: "var(--surface)",
          borderRadius: 12,
          boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
          zIndex: 10,
          maxHeight: 200,
          overflowY: "auto",
        }}>
          {searching && (
            <div style={{ padding: "10px 14px", fontSize: 12, color: "var(--label3)" }}>검색 중...</div>
          )}
          {!searching && results.length === 0 && query.trim() && (
            <div style={{ padding: "10px 14px", fontSize: 12, color: "var(--label3)" }}>결과 없음</div>
          )}
          {results.map(r => (
            <div
              key={r.stock_code}
              onClick={() => onSelect(r)}
              style={{
                padding: "9px 14px",
                cursor: "pointer",
                borderTop: "0.5px solid var(--sep)",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--label)" }}>{r.corp_name}</div>
                <div style={{ fontSize: 11, color: "var(--label3)", fontFamily: "monospace" }}>{r.stock_code}</div>
              </div>
            </div>
          ))}
          <div
            onClick={onSlotClose}
            style={{
              padding: "9px 14px",
              cursor: "pointer",
              borderTop: "0.5px solid var(--sep)",
              fontSize: 12,
              color: "var(--label3)",
              textAlign: "center",
            }}
          >
            닫기
          </div>
        </div>
      )}
    </div>
  );
}

// ─── 메인 컴포넌트 ────────────────────────────────────────────────────────────

export function CompareModal({ initialCode, initialName, onClose }: Props) {
  const [stockA, setStockA] = useState<Slot | null>(
    initialCode ? { code: initialCode, name: initialName ?? "" } : null,
  );
  const [stockB, setStockB] = useState<Slot | null>(null);
  const [period, setPeriod] = useState<"1m" | "3m" | "6m" | "1y">("3m");
  const [data, setData] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState(false);
  const [searchSlot, setSearchSlot] = useState<"A" | "B" | null>(null);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  // 두 종목 모두 선택되면 자동 조회
  useEffect(() => {
    if (!stockA || !stockB) return;
    setLoading(true);
    setFetchError(false);
    fetchCompare(stockA.code, stockB.code, period)
      .then(setData)
      .catch(() => { setData(null); setFetchError(true); })
      .finally(() => setLoading(false));
  }, [stockA, stockB, period]);

  // searchSlot 변경 시 검색 상태 초기화
  useEffect(() => {
    setQuery("");
    setSearchResults([]);
  }, [searchSlot]);

  // 검색어 300ms 디바운스
  useEffect(() => {
    if (!query.trim()) { setSearchResults([]); return; }
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const results = await searchStock(query);
        setSearchResults(results);
      } finally {
        setSearching(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  function selectStock(r: SearchResult) {
    const slot: Slot = { code: r.stock_code, name: r.corp_name };
    if (searchSlot === "A") setStockA(slot);
    else setStockB(slot);
    setSearchSlot(null);
  }

  return (
    <>
      {/* 백드롭 */}
      <div
        onClick={onClose}
        style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 199 }}
      />

      {/* 바텀 시트 패널 */}
      <div
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 200,
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "center",
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: 480,
            maxHeight: "92vh",
            background: "var(--bg)",
            borderRadius: "20px 20px 0 0",
            overflowY: "auto",
            pointerEvents: "auto",
          }}
        >
          {/* 헤더 */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px 0" }}>
            <span style={{ fontSize: 15, fontWeight: 700, color: "var(--label)" }}>종목 비교</span>
            <button
              onClick={onClose}
              style={{
                background: "none", border: "none", cursor: "pointer",
                fontSize: 16, color: "var(--label2)", padding: "4px 6px",
              }}
            >
              ✕
            </button>
          </div>

          {/* 종목 슬롯 */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 32px 1fr", alignItems: "flex-start", gap: 8, padding: "16px 20px 0" }}>
            <StockSlot
              slot={stockA} color="#007AFF" label="종목 A"
              isSearching={searchSlot === "A"}
              onOpen={() => { setSearchSlot("A"); setQuery(""); setSearchResults([]); }}
              onClose={() => setSearchSlot(null)}
              query={query} onQueryChange={setQuery}
              results={searchResults} searching={searching}
              onSelect={selectStock}
            />
            <div style={{ textAlign: "center", fontSize: 11, fontWeight: 700, color: "var(--label3)", paddingTop: 22 }}>
              VS
            </div>
            <StockSlot
              slot={stockB} color="#FF9500" label="종목 B"
              isSearching={searchSlot === "B"}
              onOpen={() => { setSearchSlot("B"); setQuery(""); setSearchResults([]); }}
              onClose={() => setSearchSlot(null)}
              query={query} onQueryChange={setQuery}
              results={searchResults} searching={searching}
              onSelect={selectStock}
            />
          </div>

          {/* 기간 선택 */}
          <div style={{ display: "flex", gap: 6, padding: "16px 20px" }}>
            {PERIODS.map(p => (
              <button
                key={p.key}
                onClick={() => setPeriod(p.key)}
                style={{
                  fontSize: 12, padding: "5px 12px", borderRadius: 7,
                  border: "none", cursor: "pointer",
                  background: period === p.key ? "#007AFF" : "rgba(118,118,128,0.12)",
                  color: period === p.key ? "#fff" : "var(--label2)",
                  fontWeight: period === p.key ? 700 : 500,
                }}
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* 로딩 상태 */}
          {loading && (
            <div style={{ padding: "24px 20px", textAlign: "center", fontSize: 13, color: "var(--label3)" }}>
              불러오는 중...
            </div>
          )}

          {/* 데이터 영역 */}
          {!loading && data && (
            <>
              {/* 레전드 */}
              <div style={{ display: "flex", gap: 20, padding: "0 20px 10px" }}>
                {([0, 1] as const).map(i => {
                  const s = data.stocks[i];
                  const ret = s.price_series.at(-1)?.return_pct ?? null;
                  const color = i === 0 ? "#007AFF" : "#FF9500";
                  const retColor = ret === null ? "var(--label2)" : ret >= 0 ? "var(--red)" : "var(--primary)";
                  return (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <div style={{ width: 24, height: 2.5, background: color, borderRadius: 2, flexShrink: 0 }} />
                      <span style={{ fontSize: 12, fontWeight: 600, color: "var(--label)" }}>
                        {s.corp_name ?? s.stock_code}
                      </span>
                      {ret !== null && (
                        <span style={{ fontSize: 12, fontWeight: 700, color: retColor }}>
                          {ret >= 0 ? "+" : ""}{ret.toFixed(1)}%
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* 차트 */}
              <div style={{ padding: "0 20px 16px" }}>
                {data.stocks[0].price_series.length === 0 && data.stocks[1].price_series.length === 0 ? (
                  <div style={{
                    height: 140,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 12, color: "var(--label3)",
                  }}>
                    가격 데이터 없음
                  </div>
                ) : (
                  <ReturnChart data={data} />
                )}
              </div>

              {/* 구분선 */}
              <div style={{ height: "0.5px", background: "var(--sep)" }} />

              {/* 지표 테이블 */}
              <div style={{ padding: "4px 0 8px" }}>
                {/* 헤더 행 */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 80px 80px", padding: "6px 20px", marginBottom: 2 }}>
                  <span style={{ fontSize: 10, fontWeight: 600, color: "var(--label3)", letterSpacing: "0.3px" }}>지표</span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: "#007AFF", textAlign: "right" }}>
                    {data.stocks[0].corp_name ?? data.stocks[0].stock_code}
                  </span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: "#FF9500", textAlign: "right" }}>
                    {data.stocks[1].corp_name ?? data.stocks[1].stock_code}
                  </span>
                </div>

                {/* 지표 행 */}
                {ROWS.map(row => {
                  const vA = data.stocks[0].metrics[row.key];
                  const vB = data.stocks[1].metrics[row.key];
                  const win = better(row.key, vA, vB);
                  return (
                    <div
                      key={row.key}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 80px 80px",
                        padding: "9px 20px",
                        borderTop: "0.5px solid rgba(118,118,128,0.12)",
                      }}
                    >
                      <span style={{ fontSize: 13, color: "var(--label2)" }}>{row.label}</span>
                      <span style={{
                        fontSize: 13, textAlign: "right",
                        fontWeight: win === "A" ? 700 : 500,
                        color: win === "A" ? "#30D158" : "var(--label)",
                      }}>
                        {row.fmt(vA)}
                      </span>
                      <span style={{
                        fontSize: 13, textAlign: "right",
                        fontWeight: win === "B" ? 700 : 500,
                        color: win === "B" ? "#30D158" : "var(--label)",
                      }}>
                        {row.fmt(vB)}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* 하단 safe area */}
              <div style={{ height: 24 }} />
            </>
          )}

          {/* 에러 상태 */}
          {!loading && fetchError && stockA && stockB && (
            <div style={{ padding: "24px 20px", textAlign: "center", fontSize: 13, color: "var(--label3)" }}>
              데이터를 불러오지 못했습니다
            </div>
          )}
        </div>
      </div>
    </>
  );
}

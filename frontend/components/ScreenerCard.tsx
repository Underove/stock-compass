// frontend/components/ScreenerCard.tsx
"use client";

import React, { useState } from "react";
import { screenStocks } from "../lib/api";
import type { ScreenerItem, ScreenerParams } from "../lib/types";
import type { PortfolioItem } from "../lib/types";
import { StockDetailModal } from "./StockDetailModal";

const SECTORS = [
  "반도체", "2차전지·전기차", "바이오·제약", "자동차",
  "IT·플랫폼", "금융·보험", "게임·엔터", "화학·소재",
  "조선·방산", "소비재·유통", "건설·인프라", "에너지·유틸리티",
];

const PER_PRESETS: { label: string; min: string; max: string }[] = [
  { label: "≤10",      min: "",    max: "10"  },
  { label: "10–20",    min: "10",  max: "20"  },
  { label: "20–40",    min: "20",  max: "40"  },
  { label: "40–100",   min: "40",  max: "100" },
  { label: "≥100",     min: "100", max: ""    },
];

const RSI_PRESETS = [
  { label: "과매도  ≤30", min: "",   max: "30" },
  { label: "중립  30–70", min: "30", max: "70" },
  { label: "과매수  ≥70", min: "70", max: ""   },
];

const MA_OPTIONS: { value: ScreenerParams["ma_status"]; label: string }[] = [
  { value: undefined,  label: "전체"      },
  { value: "golden",   label: "골든크로스" },
  { value: "dead",     label: "데드크로스" },
  { value: "above",    label: "단기 상승" },
  { value: "below",    label: "단기 하락" },
];

function fmt(n: number) { return n.toLocaleString("ko-KR"); }

function chip(active: boolean): React.CSSProperties {
  return {
    padding: "5px 12px",
    borderRadius: 100,
    fontSize: 11,
    fontWeight: active ? 700 : 600,
    background: active ? "var(--primary)" : "var(--surface)",
    color: active ? "#fff" : "var(--label)",
    border: active ? "1.5px solid transparent" : "1.5px solid var(--sep)",
    cursor: "pointer",
    transition: "background 0.12s, color 0.12s, border-color 0.12s",
    whiteSpace: "nowrap",
  };
}

function SectionLabel({ title, hint }: { title: string; hint?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
      <span style={{ fontSize: 12, fontWeight: 700, color: "var(--label)" }}>{title}</span>
      {hint && <span style={{ fontSize: 11, color: "var(--label3)", fontWeight: 400 }}>{hint}</span>}
    </div>
  );
}

const divider: React.CSSProperties = {
  borderTop: "1px solid var(--sep)",
  margin: "0",
};

export function ScreenerCard() {
  const [sector, setSector]   = useState<string | null>(null);
  const [perMin, setPerMin]   = useState("");
  const [perMax, setPerMax]   = useState("");
  const [rsiMin, setRsiMin]   = useState("");
  const [rsiMax, setRsiMax]   = useState("");
  const [maStatus, setMaStatus] = useState<ScreenerParams["ma_status"]>(undefined);
  const [results, setResults] = useState<ScreenerItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [selectedItem, setSelectedItem] = useState<PortfolioItem | null>(null);
  const latestReq = React.useRef(0);

  function buildParams(): ScreenerParams {
    return {
      ...(sector   ? { sector } : {}),
      ...(perMin   ? { per_min: parseFloat(perMin) } : {}),
      ...(perMax   ? { per_max: parseFloat(perMax) } : {}),
      ...(rsiMin   ? { rsi_min: parseFloat(rsiMin) } : {}),
      ...(rsiMax   ? { rsi_max: parseFloat(rsiMax) } : {}),
      ...(maStatus ? { ma_status: maStatus } : {}),
    };
  }

  async function run() {
    const reqId = ++latestReq.current;
    setLoading(true);
    setSearched(true);
    try {
      const data = await screenStocks(buildParams());
      if (reqId === latestReq.current) setResults(data);
    } catch {
      if (reqId === latestReq.current) setResults([]);
    } finally {
      if (reqId === latestReq.current) setLoading(false);
    }
  }

  const maStatusColor = (s: string | null) => {
    if (s === "golden") return "var(--red)";
    if (s === "dead")   return "var(--primary)";
    return "var(--label2)";
  };

  const hasFilters = !!(sector || perMin || perMax || rsiMin || rsiMax || maStatus);

  return (
    <>
      <div style={{
        background: "var(--surface)",
        borderRadius: 20,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        width: "100%",
      }}>

        {/* ── 섹터 ── */}
        <div style={{ padding: "16px 16px 14px", display: "flex", flexDirection: "column", gap: 10 }}>
          <SectionLabel title="섹터" />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {SECTORS.map(s => (
              <button
                key={s}
                onClick={() => setSector(sector === s ? null : s)}
                style={chip(sector === s)}
              >{s}</button>
            ))}
          </div>
        </div>

        <div style={divider} />

        {/* ── PER ── */}
        <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
          <SectionLabel title="PER" hint="낮을수록 저평가 · 높을수록 성장 기대" />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {PER_PRESETS.map(p => {
              const active = perMin === p.min && perMax === p.max;
              return (
                <button
                  key={p.label}
                  onClick={() => {
                    if (active) { setPerMin(""); setPerMax(""); }
                    else { setPerMin(p.min); setPerMax(p.max); }
                  }}
                  style={chip(active)}
                >{p.label}</button>
              );
            })}
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <input
              value={perMin}
              onChange={e => setPerMin(e.target.value)}
              placeholder="최소"
              type="number"
              style={{
                flex: 1, minWidth: 0, padding: "6px 10px", borderRadius: 8,
                background: "var(--surface3)", border: "none",
                fontSize: 12, color: "var(--label)",
              }}
            />
            <input
              value={perMax}
              onChange={e => setPerMax(e.target.value)}
              placeholder="최대"
              type="number"
              style={{
                flex: 1, minWidth: 0, padding: "6px 10px", borderRadius: 8,
                background: "var(--surface3)", border: "none",
                fontSize: 12, color: "var(--label)",
              }}
            />
          </div>
        </div>

        <div style={divider} />

        {/* ── RSI ── */}
        <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
          <SectionLabel title="RSI" hint="30↓ 과매도 · 70↑ 과매수" />
          <div style={{ display: "flex", gap: 6 }}>
            {RSI_PRESETS.map(p => {
              const active = rsiMin === p.min && rsiMax === p.max;
              return (
                <button
                  key={p.label}
                  onClick={() => {
                    if (active) { setRsiMin(""); setRsiMax(""); }
                    else { setRsiMin(p.min); setRsiMax(p.max); }
                  }}
                  style={{ ...chip(active), flex: 1, textAlign: "center" }}
                >{p.label}</button>
              );
            })}
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <input
              value={rsiMin}
              onChange={e => setRsiMin(e.target.value)}
              placeholder="최소"
              type="number"
              style={{
                flex: 1, minWidth: 0, padding: "6px 10px", borderRadius: 8,
                background: "var(--surface3)", border: "none",
                fontSize: 12, color: "var(--label)",
              }}
            />
            <input
              value={rsiMax}
              onChange={e => setRsiMax(e.target.value)}
              placeholder="최대"
              type="number"
              style={{
                flex: 1, minWidth: 0, padding: "6px 10px", borderRadius: 8,
                background: "var(--surface3)", border: "none",
                fontSize: 12, color: "var(--label)",
              }}
            />
          </div>
        </div>

        <div style={divider} />

        {/* ── 이동평균 ── */}
        <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
          <SectionLabel title="이동평균" />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {MA_OPTIONS.map(opt => {
              const active = maStatus === opt.value;
              return (
                <button
                  key={opt.label}
                  onClick={() => setMaStatus(active ? undefined : opt.value)}
                  style={chip(active)}
                >{opt.label}</button>
              );
            })}
          </div>
        </div>

        <div style={divider} />

        {/* ── 버튼 + 결과 ── */}
        <div style={{ padding: "14px 16px 18px", display: "flex", flexDirection: "column", gap: 12 }}>
          <button
            onClick={run}
            disabled={loading}
            style={{
              padding: "13px",
              borderRadius: 14,
              background: hasFilters ? "var(--primary)" : "var(--surface3)",
              color: hasFilters ? "#fff" : "var(--label2)",
              fontSize: 14,
              fontWeight: 700,
              opacity: loading ? 0.7 : 1,
              transition: "background 0.15s, color 0.15s, opacity 0.15s",
            }}
          >{loading ? "조회 중…" : "스크리닝"}</button>

          {searched && !loading && (
            results.length === 0 ? (
              <div style={{ textAlign: "center", padding: "8px 0" }}>
                <p style={{ fontSize: 13, color: "var(--label2)", margin: "0 0 3px" }}>
                  조건에 맞는 종목이 없어요
                </p>
                <p style={{ fontSize: 11, color: "var(--label3)", margin: 0 }}>
                  데이터는 평일 장 마감 후(16:20) 자동으로 채워져요
                </p>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                <p style={{ fontSize: 11, color: "var(--label2)", fontWeight: 600, margin: "0 0 4px" }}>
                  {results.length}개 종목
                </p>
                {results.map(item => {
                  const rsiLabel = item.rsi == null ? null
                    : item.rsi < 30 ? { text: "저평가", color: "var(--primary)", bg: "rgba(0,122,255,0.10)" }
                    : item.rsi > 70 ? { text: "과열", color: "var(--red)", bg: "rgba(255,59,48,0.10)" }
                    : { text: "중립", color: "#C9A000", bg: "rgba(255,200,0,0.12)" };
                  const maLabel = item.ma_status === "golden" ? { text: "상승신호", color: "var(--red)", bg: "rgba(255,59,48,0.10)" }
                    : item.ma_status === "dead" ? { text: "하락신호", color: "var(--primary)", bg: "rgba(0,122,255,0.10)" }
                    : item.ma_status === "above" ? { text: "상승흐름", color: "var(--red)", bg: "rgba(255,59,48,0.07)" }
                    : item.ma_status === "below" ? { text: "하락흐름", color: "var(--primary)", bg: "rgba(0,122,255,0.07)" }
                    : null;
                  return (
                    <div
                      key={item.stock_code}
                      onClick={() => setSelectedItem({
                        stock_code: item.stock_code,
                        corp_name: item.corp_name,
                        buy_price: 0,
                        quantity: 0,
                      })}
                      style={{
                        padding: "10px 12px",
                        borderRadius: 12,
                        background: "var(--surface3)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        cursor: "pointer",
                      }}
                    >
                      {/* 이름 + 서브 */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--label)", marginBottom: 3 }}>
                          {item.corp_name}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--label2)", fontWeight: 500 }}>
                          {item.sector} · {fmt(item.market_cap)}억
                        </div>
                      </div>

                      {/* 신호 배지 */}
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4, flexShrink: 0 }}>
                        {rsiLabel && (
                          <span style={{
                            fontSize: 10, fontWeight: 700,
                            color: rsiLabel.color, background: rsiLabel.bg,
                            borderRadius: 6, padding: "2px 7px",
                          }}>
                            {rsiLabel.text}
                          </span>
                        )}
                        {maLabel && (
                          <span style={{
                            fontSize: 10, fontWeight: 700,
                            color: maLabel.color, background: maLabel.bg,
                            borderRadius: 6, padding: "2px 7px",
                          }}>
                            {maLabel.text}
                          </span>
                        )}
                        {item.per != null && (
                          <span style={{ fontSize: 10, fontWeight: 600, color: "var(--label3)" }}>
                            PER {item.per}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )
          )}

          {!searched && (
            <p style={{ fontSize: 12, color: "var(--label3)", textAlign: "center", margin: "4px 0 0" }}>
              조건을 선택하고 스크리닝하세요
            </p>
          )}
        </div>
      </div>

      {selectedItem && (
        <StockDetailModal
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
        />
      )}
    </>
  );
}

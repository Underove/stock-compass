// frontend/components/ScreenerCard.tsx
"use client";

import React, { useEffect, useState } from "react";
import {
  deleteFilter, getSavedFilters, saveFilter, screenStocks,
} from "../lib/api";
import type { SavedFilter, ScreenerItem, ScreenerParams } from "../lib/types";
import type { PortfolioItem } from "../lib/types";
import { StockDetailModal } from "./StockDetailModal";

const SECTORS = [
  "반도체", "2차전지·전기차", "바이오·제약", "자동차",
  "IT·플랫폼", "금융·보험", "게임·엔터", "화학·소재",
  "조선·방산", "소비재·유통", "건설·인프라", "에너지·유틸리티",
];

const MA_OPTIONS: { value: ScreenerParams["ma_status"]; label: string }[] = [
  { value: undefined,  label: "전체" },
  { value: "golden",   label: "골든크로스" },
  { value: "dead",     label: "데드크로스" },
  { value: "above",    label: "단기 상승 중" },
  { value: "below",    label: "단기 하락 중" },
];

const PER_PRESETS = [
  { label: "가치주  ≤10",  value: "10" },
  { label: "저평가  ≤15",  value: "15" },
  { label: "성장주  ≤30",  value: "30" },
];

const RSI_PRESETS = [
  { label: "과매도  ≤30", min: "",   max: "30" },
  { label: "중립  30–70", min: "30", max: "70" },
  { label: "과매수  ≥70", min: "70", max: ""   },
];

function fmt(n: number) { return n.toLocaleString("ko-KR"); }

export function ScreenerCard() {
  const [sector, setSector]           = useState<string | null>(null);
  const [perMax, setPerMax]           = useState("");
  const [rsiMin, setRsiMin]           = useState("");
  const [rsiMax, setRsiMax]           = useState("");
  const [maStatus, setMaStatus]       = useState<ScreenerParams["ma_status"]>(undefined);
  const [results, setResults]         = useState<ScreenerItem[]>([]);
  const [loading, setLoading]         = useState(false);
  const [searched, setSearched]       = useState(false);
  const [savedFilters, setSavedFilters] = useState<SavedFilter[]>([]);
  const [showSaveInput, setShowSaveInput] = useState(false);
  const [filterName, setFilterName]   = useState("");
  const [saving, setSaving]           = useState(false);
  const [selectedItem, setSelectedItem] = useState<PortfolioItem | null>(null);
  const latestReq = React.useRef(0);

  useEffect(() => {
    getSavedFilters().then(setSavedFilters).catch(() => {});
  }, []);

  function buildParams(): ScreenerParams {
    return {
      ...(sector ? { sector } : {}),
      ...(perMax  ? { per_max:  parseFloat(perMax)  } : {}),
      ...(rsiMin  ? { rsi_min:  parseFloat(rsiMin)  } : {}),
      ...(rsiMax  ? { rsi_max:  parseFloat(rsiMax)  } : {}),
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

  function applyFilter(f: SavedFilter) {
    const p = f.params;
    setSector(p.sector ?? null);
    setPerMax(p.per_max != null ? String(p.per_max) : "");
    setRsiMin(p.rsi_min != null ? String(p.rsi_min) : "");
    setRsiMax(p.rsi_max != null ? String(p.rsi_max) : "");
    setMaStatus(p.ma_status ?? undefined);
  }

  async function handleSaveFilter() {
    if (!filterName.trim()) return;
    setSaving(true);
    try {
      const saved = await saveFilter(filterName.trim(), buildParams());
      setSavedFilters(prev => [{ id: saved.id, name: saved.name, params: buildParams(), created_at: "" }, ...prev]);
      setFilterName("");
      setShowSaveInput(false);
    } catch {
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteFilter(id: number) {
    try {
      await deleteFilter(id);
      setSavedFilters(prev => prev.filter(f => f.id !== id));
    } catch {
      // server delete failed; keep filter in list
    }
  }

  function openDetail(item: ScreenerItem) {
    setSelectedItem({ stock_code: item.stock_code, corp_name: item.corp_name, buy_price: 0, quantity: 0 });
  }

  const maStatusColor = (s: string | null) => {
    if (s === "golden") return "var(--red)";
    if (s === "dead")   return "var(--primary)";
    return "var(--label2)";
  };

  return (
    <>
      <div style={{
        background: "var(--surface)",
        borderRadius: 20,
        padding: "16px 16px 20px",
        display: "flex", flexDirection: "column", gap: 16,
        minWidth: 0, width: "100%",
      }}>
        {/* 필터 저장 버튼 */}
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button
            onClick={() => setShowSaveInput(v => !v)}
            style={{
              padding: "5px 12px", borderRadius: 100,
              background: "var(--surface3)", fontSize: 12, fontWeight: 600, color: "var(--label2)",
            }}
          >
            필터 저장
          </button>
        </div>

        {/* 저장된 필터 */}
        {savedFilters.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {savedFilters.map(f => (
              <div key={f.id} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <button
                  onClick={() => applyFilter(f)}
                  style={{
                    padding: "5px 10px", borderRadius: 100,
                    background: "var(--surface3)", fontSize: 11, fontWeight: 600, color: "var(--label)",
                    border: "1px solid var(--sep)",
                  }}
                >{f.name}</button>
                <button
                  aria-label={`${f.name} 필터 삭제`}
                  onClick={() => handleDeleteFilter(f.id)}
                  style={{ width: 16, height: 16, borderRadius: "50%", background: "var(--surface3)", display: "flex", alignItems: "center", justifyContent: "center" }}
                >
                  <svg aria-hidden="true" width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="var(--label3)" strokeWidth="2.5" strokeLinecap="round">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}

        {/* 필터 이름 입력 */}
        {showSaveInput && (
          <div style={{ display: "flex", gap: 8 }}>
            <input
              value={filterName}
              onChange={e => setFilterName(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSaveFilter()}
              placeholder="필터 이름 입력 후 엔터"
              style={{
                flex: 1, minWidth: 0, padding: "8px 12px", borderRadius: 10,
                background: "var(--surface3)", border: "1px solid var(--sep)",
                fontSize: 13, color: "var(--label)",
              }}
            />
            <button
              onClick={handleSaveFilter}
              disabled={saving}
              style={{
                padding: "8px 14px", borderRadius: 10,
                background: "var(--primary)", color: "white",
                fontSize: 12, fontWeight: 700,
              }}
            >{saving ? "…" : "저장"}</button>
          </div>
        )}

        {/* 섹터 칩 */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {SECTORS.map(s => {
            const active = sector === s;
            return (
              <button
                key={s}
                onClick={() => setSector(active ? null : s)}
                style={{
                  padding: "5px 12px", borderRadius: 100,
                  fontSize: 12, fontWeight: active ? 700 : 600,
                  background: "var(--surface)",
                  color: active ? "var(--primary)" : "var(--label)",
                  border: active ? "1.5px solid var(--primary)" : "1.5px solid var(--sep)",
                  transition: "all 0.14s",
                }}
              >{s}</button>
            );
          })}
        </div>

        {/* 가치 지표 */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <span style={{ fontSize: 11, color: "var(--label2)", fontWeight: 700 }}>PER <span style={{ fontWeight: 400 }}>(낮을수록 저평가)</span></span>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {PER_PRESETS.map(p => {
              const active = perMax === p.value;
              return (
                <button
                  key={p.value}
                  onClick={() => setPerMax(active ? "" : p.value)}
                  style={{
                    padding: "5px 12px", borderRadius: 100,
                    fontSize: 11, fontWeight: active ? 700 : 600,
                    background: "var(--surface)",
                    color: active ? "var(--primary)" : "var(--label2)",
                    border: active ? "1.5px solid var(--primary)" : "1.5px solid var(--sep)",
                    transition: "all 0.14s",
                  }}
                >{p.label}</button>
              );
            })}
          </div>
          <input
            value={perMax}
            onChange={e => setPerMax(e.target.value)}
            placeholder="직접 입력 (예: 20)"
            type="number"
            style={{
              width: "100%", padding: "7px 10px", borderRadius: 10,
              background: "var(--surface3)", border: "1px solid var(--sep)",
              fontSize: 13, color: "var(--label)",
            }}
          />
        </div>

        {/* RSI */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <span style={{ fontSize: 11, color: "var(--label2)", fontWeight: 700 }}>RSI</span>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {RSI_PRESETS.map(p => {
              const active = rsiMin === p.min && rsiMax === p.max;
              return (
                <button
                  key={p.label}
                  onClick={() => {
                    if (active) { setRsiMin(""); setRsiMax(""); }
                    else { setRsiMin(p.min); setRsiMax(p.max); }
                  }}
                  style={{
                    padding: "5px 12px", borderRadius: 100,
                    fontSize: 11, fontWeight: active ? 700 : 600,
                    background: "var(--surface)",
                    color: active ? "var(--primary)" : "var(--label2)",
                    border: active ? "1.5px solid var(--primary)" : "1.5px solid var(--sep)",
                    transition: "all 0.14s",
                  }}
                >{p.label}</button>
              );
            })}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              value={rsiMin}
              onChange={e => setRsiMin(e.target.value)}
              placeholder="최소"
              type="number"
              style={{
                flex: 1, width: "100%", padding: "7px 10px", borderRadius: 10,
                background: "var(--surface3)", border: "1px solid var(--sep)",
                fontSize: 13, color: "var(--label)",
              }}
            />
            <input
              value={rsiMax}
              onChange={e => setRsiMax(e.target.value)}
              placeholder="최대"
              type="number"
              style={{
                flex: 1, width: "100%", padding: "7px 10px", borderRadius: 10,
                background: "var(--surface3)", border: "1px solid var(--sep)",
                fontSize: 13, color: "var(--label)",
              }}
            />
          </div>
        </div>

        {/* MA 상태 */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={{ fontSize: 11, color: "var(--label2)", fontWeight: 700 }}>이동평균 추세</span>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {MA_OPTIONS.map(opt => {
            const active = maStatus === opt.value;
            return (
              <button
                key={opt.label}
                onClick={() => setMaStatus(active ? undefined : opt.value)}
                style={{
                  padding: "5px 12px", borderRadius: 100,
                  fontSize: 11, fontWeight: active ? 700 : 600,
                  background: "var(--surface)",
                  color: active ? "var(--primary)" : "var(--label2)",
                  border: active ? "1.5px solid var(--primary)" : "1.5px solid var(--sep)",
                  transition: "all 0.14s",
                }}
              >{opt.label}</button>
            );
          })}
          </div>
        </div>

        {/* 스크리닝 버튼 */}
        <button
          onClick={run}
          disabled={loading}
          style={{
            padding: "12px", borderRadius: 14,
            background: "var(--primary)", color: "white",
            fontSize: 14, fontWeight: 700,
            boxShadow: "0 4px 14px rgba(0,122,255,0.28)",
            opacity: loading ? 0.7 : 1,
            transition: "opacity 0.2s",
          }}
        >{loading ? "조회 중…" : "스크리닝"}</button>

        {/* 결과 */}
        {searched && !loading && (
          results.length === 0 ? (
            <div style={{ textAlign: "center", margin: "8px 0 0" }}>
              <p style={{ fontSize: 13, color: "var(--label2)", margin: "0 0 4px" }}>조건에 맞는 종목이 없어요</p>
              <p style={{ fontSize: 11, color: "var(--label3)", margin: 0 }}>데이터는 평일 장 마감 후(16:20) 자동으로 채워져요</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <p style={{ fontSize: 11, color: "var(--label2)", fontWeight: 600, margin: "0 0 6px" }}>
                {results.length}개 종목
              </p>
              {results.map(item => (
                <button
                  key={item.stock_code}
                  onClick={() => openDetail(item)}
                  style={{
                    padding: "11px 12px",
                    borderRadius: 12,
                    background: "var(--surface3)",
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    textAlign: "left",
                    border: "none",
                    cursor: "pointer",
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "var(--label)" }}>
                      {item.corp_name}
                    </span>
                    <span style={{ fontSize: 11, color: "var(--label2)", fontWeight: 600 }}>
                      {item.sector} · 시총 {fmt(item.market_cap)}억
                    </span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3 }}>
                    {item.rsi != null && (
                      <span style={{ fontSize: 11, fontWeight: 600, color: item.rsi < 30 ? "var(--primary)" : item.rsi > 70 ? "var(--red)" : "var(--label2)" }}>
                        RSI {item.rsi}
                      </span>
                    )}
                    {item.per != null && (
                      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--label2)" }}>
                        PER {item.per}
                      </span>
                    )}
                    {item.ma_status && item.ma_status !== "none" && (
                      <span style={{ fontSize: 10, fontWeight: 700, color: maStatusColor(item.ma_status) }}>
                        {item.ma_status === "golden" ? "골든" : item.ma_status === "dead" ? "데드" : item.ma_status}
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )
        )}

        {!searched && (
          <p style={{ fontSize: 13, color: "var(--label2)", textAlign: "center", margin: "4px 0 0" }}>
            조건을 설정하고 스크리닝해보세요
          </p>
        )}
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

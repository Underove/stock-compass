"use client";

import React, { useEffect, useState } from "react";
import { getProfile, updateProfile } from "../lib/api";
import type { UserProfile } from "../lib/types";

const RISK_OPTIONS: { value: UserProfile["risk_level"]; label: string; desc: string }[] = [
  { value: "aggressive", label: "공격적", desc: "고위험·고수익" },
  { value: "neutral",    label: "중립",   desc: "균형 투자" },
  { value: "defensive",  label: "방어적", desc: "안정 우선" },
];

const HORIZON_OPTIONS: { value: UserProfile["horizon"]; label: string; desc: string }[] = [
  { value: "short", label: "단기", desc: "1년 미만" },
  { value: "mid",   label: "중기", desc: "1~3년" },
  { value: "long",  label: "장기", desc: "3년 이상" },
];

const ALL_SECTORS = [
  "반도체", "2차전지·전기차", "바이오·제약", "자동차",
  "IT·플랫폼", "금융·보험", "게임·엔터", "화학·소재",
  "조선·방산", "소비재·유통", "건설·인프라", "에너지·유틸리티",
];

const MAX_SECTORS = 4;

export function ProfileSettings({ onClose }: { onClose: () => void }) {
  const [riskLevel, setRiskLevel] = useState<UserProfile["risk_level"]>("neutral");
  const [horizon, setHorizon]     = useState<UserProfile["horizon"]>("mid");
  const [sectors, setSectors]     = useState<string[]>([]);
  const [aiMemo, setAiMemo]       = useState("");
  const [saving, setSaving]       = useState(false);
  const [saved, setSaved]         = useState(false);
  const [error, setError]         = useState<string | null>(null);

  useEffect(() => {
    getProfile()
      .then(p => {
        setRiskLevel(p.risk_level);
        setHorizon(p.horizon);
        setSectors(p.sectors);
        setAiMemo(p.ai_memo);
      })
      .catch(() => {});
  }, []);

  function toggleSector(s: string) {
    setSectors(prev => {
      if (prev.includes(s)) return prev.filter(x => x !== s);
      if (prev.length >= MAX_SECTORS) return prev;
      return [...prev, s];
    });
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await updateProfile({ risk_level: riskLevel, horizon, sectors });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{
      position: "absolute", inset: 0,
      background: "var(--bg)",
      display: "flex", flexDirection: "column",
      zIndex: 10,
    }}>
      {/* 헤더 */}
      <div style={{
        padding: "14px 16px 12px",
        borderBottom: "0.5px solid var(--sep)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        flexShrink: 0,
      }}>
        <span style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.03em" }}>투자 성향</span>
        <button
          onClick={onClose}
          style={{
            width: 28, height: 28, borderRadius: "50%",
            background: "var(--surface3)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--label2)" strokeWidth="2.5" strokeLinecap="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* 스크롤 영역 */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px 16px 32px", display: "flex", flexDirection: "column", gap: 24 }}>

        {/* 리스크 성향 */}
        <Section label="리스크 성향">
          <div style={{ display: "flex", gap: 8 }}>
            {RISK_OPTIONS.map(opt => {
              const active = riskLevel === opt.value;
              return (
                <button
                  key={opt.value}
                  onClick={() => setRiskLevel(opt.value)}
                  style={{
                    flex: 1, padding: "12px 8px",
                    borderRadius: 14,
                    background: "var(--surface)",
                    border: active ? "1.5px solid var(--primary)" : "1.5px solid var(--sep)",
                    boxShadow: active ? "var(--shadow)" : "var(--shadow-sm)",
                    display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
                    transition: "all 0.15s",
                  }}
                >
                  <span style={{ fontSize: 13, fontWeight: active ? 800 : 600, color: active ? "var(--primary)" : "var(--label)" }}>
                    {opt.label}
                  </span>
                  <span style={{ fontSize: 10, color: active ? "var(--primary)" : "var(--label2)", opacity: active ? 0.75 : 1 }}>
                    {opt.desc}
                  </span>
                </button>
              );
            })}
          </div>
        </Section>

        {/* 투자 기간 */}
        <Section label="투자 기간">
          <div style={{ display: "flex", gap: 8 }}>
            {HORIZON_OPTIONS.map(opt => {
              const active = horizon === opt.value;
              return (
                <button
                  key={opt.value}
                  onClick={() => setHorizon(opt.value)}
                  style={{
                    flex: 1, padding: "12px 8px",
                    borderRadius: 14,
                    background: "var(--surface)",
                    border: active ? "1.5px solid var(--primary)" : "1.5px solid var(--sep)",
                    boxShadow: active ? "var(--shadow)" : "var(--shadow-sm)",
                    display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
                    transition: "all 0.15s",
                  }}
                >
                  <span style={{ fontSize: 13, fontWeight: active ? 800 : 600, color: active ? "var(--primary)" : "var(--label)" }}>
                    {opt.label}
                  </span>
                  <span style={{ fontSize: 10, color: active ? "var(--primary)" : "var(--label2)", opacity: active ? 0.75 : 1 }}>
                    {opt.desc}
                  </span>
                </button>
              );
            })}
          </div>
        </Section>

        {/* 관심 섹터 */}
        <Section label={`관심 섹터 (${sectors.length}/${MAX_SECTORS})`}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
            {ALL_SECTORS.map(s => {
              const selected = sectors.includes(s);
              const maxed = !selected && sectors.length >= MAX_SECTORS;
              return (
                <button
                  key={s}
                  onClick={() => !maxed && toggleSector(s)}
                  style={{
                    padding: "7px 14px",
                    borderRadius: 100,
                    fontSize: 12, fontWeight: selected ? 700 : 600,
                    background: "var(--surface)",
                    color: selected ? "var(--primary)" : "var(--label)",
                    border: selected ? "1.5px solid var(--primary)" : "1.5px solid var(--sep)",
                    boxShadow: selected ? "var(--shadow-sm)" : "none",
                    opacity: maxed ? 0.5 : 1,
                    cursor: maxed ? "not-allowed" : "pointer",
                    transition: "all 0.14s",
                  }}
                >
                  {s}
                </button>
              );
            })}
          </div>
          {sectors.length >= MAX_SECTORS && (
            <p style={{ fontSize: 11, color: "var(--label3)", margin: 0 }}>
              최대 {MAX_SECTORS}개까지 고를 수 있어요
            </p>
          )}
        </Section>

        {/* AI 메모 (읽기 전용) */}
        {aiMemo && (
          <Section label="AI 분석 메모">
            <div style={{
              background: "var(--surface)", borderRadius: 14, padding: "13px 15px",
              border: "0.5px solid var(--sep)",
            }}>
              <p style={{ fontSize: 13, color: "var(--label2)", lineHeight: 1.75, margin: 0 }}>{aiMemo}</p>
              <p style={{ fontSize: 11, color: "var(--label3)", margin: "8px 0 0" }}>채팅을 통해 자동으로 업데이트됩니다</p>
            </div>
          </Section>
        )}
      </div>

      {/* 저장 버튼 */}
      <div style={{
        padding: "10px 16px 20px",
        borderTop: "0.5px solid var(--sep)",
        flexShrink: 0,
        display: "flex", flexDirection: "column", gap: 8,
      }}>
        {error && (
          <p style={{ fontSize: 12, color: "var(--red)", margin: 0, textAlign: "center" }}>{error}</p>
        )}
        <button
          onClick={save}
          disabled={saving}
          style={{
            width: "100%", padding: "13px",
            borderRadius: 14,
            background: saved ? "var(--green)" : "var(--primary)",
            color: "white",
            fontSize: 14, fontWeight: 700,
            boxShadow: saved
              ? "0 4px 14px rgba(52,199,89,0.28)"
              : "0 4px 14px rgba(0,122,255,0.28)",
            transition: "all 0.2s",
            opacity: saving ? 0.7 : 1,
          }}
        >
          {saving ? "저장 중…" : saved ? "저장됨" : "성향 저장"}
        </button>
      </div>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <p style={{ fontSize: 12, fontWeight: 600, color: "var(--label2)", margin: 0 }}>
        {label}
      </p>
      {children}
    </div>
  );
}

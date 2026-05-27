"use client";

import type { FactcheckClaim, FactcheckResult, FactcheckState } from "../lib/types";

const SIGNAL: Record<
  FactcheckResult["signal"],
  { color: string; bg: string; title: string; desc: string }
> = {
  green: {
    color: "var(--green)",
    bg: "rgba(52,199,89,0.12)",
    title: "확인된 사실",
    desc: "공식 자료가 이 정보를 뒷받침해요.",
  },
  yellow: {
    color: "var(--orange)",
    bg: "rgba(255,149,0,0.12)",
    title: "검증 부족 주의",
    desc: "확인 가능한 공식 근거가 부족해요.",
  },
  red: {
    color: "var(--red)",
    bg: "rgba(255,59,48,0.12)",
    title: "허위 정보 위험",
    desc: "공식 자료와 모순되는 내용이 있어요.",
  },
};

const VERDICT: Record<string, { color: string; label: string }> = {
  지지: { color: "var(--green)", label: "사실 확인" },
  모순: { color: "var(--red)", label: "모순" },
  근거없음: { color: "var(--orange)", label: "근거 없음" },
};

export function FactcheckPanel({
  state,
  onRun,
}: {
  state: FactcheckState;
  onRun: () => void;
}) {
  if (state.kind === "idle") {
    return (
      <button
        onClick={onRun}
        style={{
          width: "100%",
          padding: "16px",
          background: "var(--primary)",
          color: "white",
          borderRadius: 14,
          fontSize: 17,
          fontWeight: 600,
          letterSpacing: "-0.02em",
          transition: "opacity 0.15s",
        }}
        onMouseEnter={(e) => ((e.target as HTMLElement).style.opacity = "0.85")}
        onMouseLeave={(e) => ((e.target as HTMLElement).style.opacity = "1")}
      >
        팩트체크 시작
      </button>
    );
  }

  if (state.kind === "running") {
    return (
      <div
        style={{
          background: "var(--bg)",
          borderRadius: 16,
          padding: "32px 24px",
          textAlign: "center",
        }}
      >
        <div
          style={{
            width: 44,
            height: 44,
            border: "3px solid var(--sep)",
            borderTopColor: "var(--primary)",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
            margin: "0 auto 16px",
          }}
        />
        <div style={{ fontSize: 17, fontWeight: 600 }}>AI 분석 중</div>
        <div style={{ fontSize: 15, color: "var(--label2)", marginTop: 6 }}>
          주장 추출 → 공시 조회 → 교차검증
        </div>
        <div style={{ fontSize: 13, color: "var(--label3)", marginTop: 8 }}>
          최대 30초 소요
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div
        style={{
          background: "rgba(255,59,48,0.08)",
          borderRadius: 16,
          padding: "20px",
        }}
      >
        <div style={{ fontSize: 17, fontWeight: 600, color: "var(--red)", marginBottom: 6 }}>
          팩트체크 실패
        </div>
        <div style={{ fontSize: 15, color: "var(--red)", opacity: 0.8 }}>{state.message}</div>
      </div>
    );
  }

  const { result } = state;
  const s = SIGNAL[result.signal];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* 신호 카드 */}
      <div
        style={{
          background: s.bg,
          borderRadius: 20,
          padding: "24px 20px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 16 }}>
          {/* 신호 아이콘 (원 → 사각 정제) */}
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 16,
              background: s.color,
              flexShrink: 0,
              boxShadow: `0 4px 16px ${s.color}40`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <SignalIcon signal={result.signal} />
          </div>
          <div>
            <div
              style={{
                fontSize: 20,
                fontWeight: 800,
                letterSpacing: "-0.04em",
                marginBottom: 4,
              }}
            >
              {s.title}
            </div>
            <div style={{ fontSize: 13, color: "var(--label2)", lineHeight: 1.5 }}>{s.desc}</div>
          </div>
        </div>

        {/* 스코어 바 */}
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--label2)", marginBottom: 6 }}>
          <span>신뢰도</span>
          <span style={{ fontWeight: 700, color: s.color }}>{result.score} / 100</span>
        </div>
        <div
          style={{
            width: "100%",
            height: 8,
            background: "rgba(0,0,0,0.08)",
            borderRadius: 4,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${result.score}%`,
              background: s.color,
              borderRadius: 4,
              transition: "width 0.9s cubic-bezier(0.34,1.56,0.64,1)",
            }}
          />
        </div>
      </div>

      {/* 탐지된 종목 */}
      {result.companies_detected.length > 0 && (
        <div
          style={{
            background: "var(--surface)",
            borderRadius: 14,
            padding: "14px 16px",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--label2)", marginBottom: 10 }}>
            탐지된 종목
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {result.companies_detected.map((c) => (
              <span
                key={c.stock_code}
                style={{
                  background: "rgba(0,122,255,0.1)",
                  color: "var(--primary)",
                  borderRadius: 100,
                  padding: "5px 12px",
                  fontSize: 14,
                  fontWeight: 600,
                }}
              >
                {c.name}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 주장별 판정 */}
      {result.claims.length > 0 && (
        <div>
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: "var(--label2)",
              marginBottom: 10,
            }}
          >
            주장별 판정 ({result.claims.length}개)
          </div>
          <div
            style={{
              background: "var(--surface)",
              borderRadius: 16,
              boxShadow: "var(--shadow-sm)",
              overflow: "hidden",
            }}
          >
            {result.claims.map((c, i) => (
              <div key={i}>
                {i > 0 && (
                  <div style={{ height: "0.5px", background: "var(--sep)", marginLeft: 16 }} />
                )}
                <ClaimRow claim={c} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SignalIcon({ signal }: { signal: FactcheckResult["signal"] }) {
  if (signal === "green") {
    return (
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
        <path d="M5 13L9 17L19 7" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (signal === "red") {
    return (
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
        <path d="M18 6L6 18M6 6L18 18" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
      <path d="M12 8V13M12 16.5V17" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

function ClaimRow({ claim }: { claim: FactcheckClaim }) {
  const v = VERDICT[claim.verdict] ?? { color: "var(--label2)", label: claim.verdict };
  return (
    <details style={{ padding: "0" }}>
      <summary
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "14px 16px",
          cursor: "pointer",
          listStyle: "none",
        }}
      >
        <span
          style={{
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: v.color,
            flexShrink: 0,
          }}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 15,
              color: "var(--label)",
              lineHeight: 1.4,
              overflow: "hidden",
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
            }}
          >
            {claim.claim}
          </div>
          <div style={{ fontSize: 13, color: v.color, fontWeight: 600, marginTop: 3 }}>
            {v.label}
          </div>
        </div>
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          style={{ flexShrink: 0, color: "var(--label3)" }}
        >
          <path d="M4 6L8 10L12 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </summary>
      <div
        style={{
          padding: "0 16px 16px 38px",
          fontSize: 14,
          color: "var(--label2)",
          lineHeight: 1.6,
        }}
      >
        <p style={{ margin: "0 0 10px" }}>{claim.reasoning}</p>
        {claim.sources.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {claim.sources.slice(0, 2).map((s, i) => (
              <div
                key={i}
                style={{
                  background: "var(--bg)",
                  borderRadius: 10,
                  padding: "10px 12px",
                  fontSize: 13,
                }}
              >
                <div style={{ color: "var(--label)", lineHeight: 1.5 }}>
                  {s.snippet.length > 150 ? `${s.snippet.slice(0, 150)}…` : s.snippet}
                </div>
                <div style={{ color: "var(--label3)", marginTop: 4, fontSize: 12 }}>
                  {s.label}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </details>
  );
}

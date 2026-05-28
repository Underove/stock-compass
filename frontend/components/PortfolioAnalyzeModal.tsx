"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, ExternalLink, FileText, Loader2, Minus, Newspaper, Sparkles, TrendingUp, X } from "lucide-react";

import { analyzePortfolio, getUploadOriginalUrl } from "../lib/api";
import type { AnalysisResult, AnalysisSource } from "../lib/types";
import { showToast } from "../hooks/useToast";

type State =
  | { kind: "loading" }
  | { kind: "done"; result: AnalysisResult }
  | { kind: "error"; message: string };

const VERDICT: Record<string, { color: string; bg: string }> = {
  "긍정": { color: "var(--red)", bg: "rgba(255,59,48,0.1)" },
  "주의": { color: "var(--orange)", bg: "rgba(255,149,0,0.1)" },
  "중립": { color: "var(--label3)", bg: "var(--surface2)" },
};

function SourceIcon({ type }: { type: AnalysisSource["type"] }) {
  if (type === "news") return <Newspaper size={14} strokeWidth={2.2} color="var(--label2)" />;
  return <FileText size={14} strokeWidth={2.2} color={type === "dart" ? "var(--primary)" : "var(--orange)"} />;
}

function sourceKind(type: AnalysisSource["type"]) {
  return type === "dart" ? "DART 공시" : type === "upload" ? "내 자료" : "뉴스";
}

export function PortfolioAnalyzeModal({ onClose }: { onClose: () => void }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let alive = true;
    analyzePortfolio()
      .then(result => { if (alive) setState({ kind: "done", result }); })
      .catch(() => { if (alive) setState({ kind: "error", message: "분석에 실패했어요. 잠시 후 다시 시도해주세요." }); });
    return () => { alive = false; };
  }, []);

  async function openSource(src: AnalysisSource) {
    if (src.type === "upload" && src.upload_id) {
      const url = await getUploadOriginalUrl(src.upload_id);
      if (url) window.open(url, "_blank");
      else showToast("원본을 불러오지 못했어요", "error");
      return;
    }
    if (src.url) window.open(src.url, "_blank");
  }

  return (
    <>
      <div
        className="modal-backdrop-enter"
        onClick={onClose}
        style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 199 }}
      />
      <div
        className="modal-enter"
        style={{ position: "fixed", inset: 0, zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}
      >
        <div
          onClick={e => e.stopPropagation()}
          style={{
            width: "100%", maxWidth: 480, maxHeight: "84vh",
            display: "flex", flexDirection: "column",
            background: "var(--bg)", borderRadius: 20, overflow: "hidden",
            boxShadow: "0 12px 40px rgba(0,0,0,0.3)",
          }}
        >
          {/* 헤더 */}
          <div style={{
            flexShrink: 0, display: "flex", alignItems: "center", gap: 8,
            padding: "16px 18px 13px", borderBottom: "0.5px solid var(--sep)",
          }}>
            <Sparkles size={17} strokeWidth={2.2} color="var(--primary)" />
            <div style={{ fontSize: 15, fontWeight: 800, color: "var(--label)", letterSpacing: "-0.02em" }}>
              AI 포트폴리오 분석
            </div>
            <button
              onClick={onClose}
              style={{ marginLeft: "auto", background: "none", border: "none", cursor: "pointer", color: "var(--label2)", display: "flex" }}
            >
              <X size={18} strokeWidth={2.2} />
            </button>
          </div>

          {/* 본문 */}
          <div style={{ flex: 1, overflowY: "auto", padding: "16px 18px" }}>
            {state.kind === "loading" && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, padding: "44px 0", color: "var(--label2)" }}>
                <Loader2 size={22} strokeWidth={2.2} color="var(--primary)" style={{ animation: "spin 1s linear infinite" }} />
                <div style={{ fontSize: 13 }}>보유 종목·공시·내 자료를 종합하는 중이에요…</div>
              </div>
            )}

            {state.kind === "error" && (
              <div style={{ padding: "40px 0", textAlign: "center", fontSize: 13, color: "var(--label2)", lineHeight: 1.6 }}>
                {state.message}
              </div>
            )}

            {state.kind === "done" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {/* 요약 */}
                <p style={{ fontSize: 15, color: "var(--label)", lineHeight: 1.65, margin: 0, letterSpacing: "-0.015em", fontWeight: 500 }}>
                  {state.result.summary}
                </p>

                {/* 종목별 평가 */}
                {state.result.holdings.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {state.result.holdings.map((h, i) => {
                      const v = VERDICT[h.verdict] ?? VERDICT["중립"];
                      const VIcon = h.verdict === "긍정" ? TrendingUp : h.verdict === "주의" ? AlertTriangle : Minus;
                      return (
                        <div key={i} style={{
                          borderRadius: 12, padding: "12px 14px",
                          background: "var(--surface2)", borderLeft: `3px solid ${v.color}`,
                          display: "flex", flexDirection: "column", gap: 5,
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                            <span style={{ fontSize: 14, fontWeight: 700, letterSpacing: "-0.022em", color: "var(--label)" }}>{h.corp_name}</span>
                            {h.change_note && (
                              <span style={{ fontSize: 11, fontWeight: 700, color: "var(--label2)", fontVariantNumeric: "tabular-nums" }}>{h.change_note}</span>
                            )}
                            <span style={{
                              marginLeft: "auto", display: "flex", alignItems: "center", gap: 3,
                              fontSize: 10, fontWeight: 700, color: v.color, background: v.bg,
                              borderRadius: 5, padding: "2px 7px",
                            }}>
                              <VIcon size={10} strokeWidth={2.6} />
                              {h.verdict}
                            </span>
                          </div>
                          <p style={{ fontSize: 13, color: "var(--label)", lineHeight: 1.6, margin: 0, letterSpacing: "-0.015em" }}>{h.comment}</p>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* 확인 체크리스트 */}
                {state.result.action_items.length > 0 && (
                  <div style={{ background: "rgba(0,122,255,0.04)", borderRadius: 14, padding: "14px 16px", border: "0.5px solid rgba(0,122,255,0.12)" }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "var(--primary)", marginBottom: 10, letterSpacing: "-0.01em" }}>확인해볼 포인트</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {state.result.action_items.map((item, i) => (
                        <div key={i} style={{ display: "flex", gap: 9, alignItems: "flex-start" }}>
                          <div style={{ width: 20, height: 20, borderRadius: 6, border: "1.5px solid rgba(0,122,255,0.35)", flexShrink: 0, marginTop: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
                            <span style={{ fontSize: 11, color: "var(--primary)", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{i + 1}</span>
                          </div>
                          <p style={{ fontSize: 14, color: "var(--label)", lineHeight: 1.55, margin: 0, letterSpacing: "-0.015em" }}>{item}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 참고 자료 (출처) */}
                {state.result.sources.length > 0 && (
                  <div style={{ borderTop: "0.5px solid var(--sep)", paddingTop: 14 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "var(--label2)", marginBottom: 9, letterSpacing: "-0.01em" }}>
                      참고한 자료 {state.result.sources.length}건
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {state.result.sources.map((src, i) => {
                        const clickable = src.type === "upload" ? !!src.upload_id : !!src.url;
                        return (
                          <button
                            key={i}
                            onClick={clickable ? () => openSource(src) : undefined}
                            className={clickable ? "tap-feedback" : undefined}
                            style={{
                              display: "flex", alignItems: "center", gap: 9, width: "100%", textAlign: "left",
                              padding: "10px 12px", background: "var(--surface2)", borderRadius: 11,
                              border: "none", cursor: clickable ? "pointer" : "default", opacity: clickable ? 1 : 0.7,
                            }}
                          >
                            <SourceIcon type={src.type} />
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--label)", letterSpacing: "-0.01em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {src.label || sourceKind(src.type)}
                              </div>
                              {src.snippet && (
                                <div style={{ fontSize: 11, color: "var(--label3)", lineHeight: 1.4, marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                  {src.snippet}
                                </div>
                              )}
                            </div>
                            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--label3)", flexShrink: 0 }}>{sourceKind(src.type)}</span>
                            {clickable && <ExternalLink size={13} strokeWidth={2.2} color="var(--label3)" style={{ flexShrink: 0 }} />}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 투자 책임 고지 */}
          <div style={{
            flexShrink: 0, padding: "6px 16px",
            borderTop: "0.5px solid var(--sep)", background: "var(--bg)",
            fontSize: 10, color: "var(--label3)", lineHeight: 1.4, textAlign: "center",
          }}>
            AI 분석은 투자 참고용이며 자문이 아니에요. 투자 판단·책임은 본인에게 있습니다.
          </div>
        </div>
      </div>
    </>
  );
}

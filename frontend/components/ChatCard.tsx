"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { ask, fetchPortfolioBriefing, fetchPremarketNews, generatePremarketNews } from "../lib/api";
import type { PremarketNews } from "../lib/api";
import type { ChatTurn, CompanySynced, PortfolioBriefing, PortfolioStats, Source } from "../lib/types";
import { ProfileSettings } from "./ProfileSettings";
import { UploadCard } from "./UploadCard";

type Tab = "briefing" | "news" | "chat" | "factcheck";

export function ChatCard({ portfolioVersion = 0 }: { portfolioVersion?: number } = {}) {
  const [activeTab, setActiveTab] = useState<Tab>("briefing");
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [isAsking, setIsAsking] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // 브리핑 상태
  const [briefing, setBriefing] = useState<PortfolioBriefing | null>(null);
  const [loadingBriefing, setLoadingBriefing] = useState(false);
  const [briefingError, setBriefingError] = useState<string | null>(null);

  // 뉴스 요약 상태
  const [premarketNews, setPremarketNews] = useState<PremarketNews | null>(null);
  const [loadingNews, setLoadingNews] = useState(false);
  const [newsLoaded, setNewsLoaded] = useState(false);
  const [generatingNews, setGeneratingNews] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const loadBriefing = useCallback(async (force = false) => {
    setLoadingBriefing(true);
    setBriefingError(null);
    try {
      const data = await fetchPortfolioBriefing(force);
      setBriefing(data);
    } catch (err) {
      setBriefingError(err instanceof Error ? err.message : "브리핑 로드 실패");
    } finally {
      setLoadingBriefing(false);
    }
  }, []);

  // 포트폴리오 변경 시 캐시 무시하고 강제 재생성
  useEffect(() => {
    if (portfolioVersion > 0) {
      setBriefing(null);
      setBriefingError(null);
      loadBriefing(true);
    }
  }, [portfolioVersion, loadBriefing]);

  // 브리핑 탭 진입 시 자동 로드 (에러 시 재시도 안 함)
  useEffect(() => {
    if (activeTab === "briefing" && !briefing && !loadingBriefing && !briefingError) {
      loadBriefing();
    }
  }, [activeTab, briefing, loadingBriefing, loadBriefing, briefingError]);

  // 뉴스 탭 진입 시 자동 로드 (한 번만)
  useEffect(() => {
    if (activeTab === "news" && !premarketNews && !loadingNews && !newsLoaded) {
      setLoadingNews(true);
      fetchPremarketNews()
        .then(d => setPremarketNews(d))
        .catch(() => {})
        .finally(() => { setLoadingNews(false); setNewsLoaded(true); });
    }
  }, [activeTab, premarketNews, loadingNews, newsLoaded]);

  const refreshNews = useCallback(async () => {
    if (generatingNews) return;
    setGeneratingNews(true);
    setPremarketNews(null);
    try {
      const data = await generatePremarketNews();
      setPremarketNews(data);
      setNewsLoaded(true);
    } catch {
      setNewsLoaded(false); // 실패 시 재시도 허용
    } finally {
      setGeneratingNews(false);
    }
  }, [generatingNews]);

  async function send() {
    const question = input.trim();
    if (!question || isAsking) return;
    const turnId = Date.now();
    setTurns(prev => [
      ...prev,
      { id: turnId, question, answer: null, sources: [], error: null, companies_synced: [] },
    ]);
    setInput("");
    setIsAsking(true);
    try {
      const data = await ask(question);
      setTurns(prev =>
        prev.map(t =>
          t.id === turnId
            ? { ...t, answer: data.answer, sources: data.sources, companies_synced: data.companies_synced ?? [] }
            : t,
        ),
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "알 수 없는 오류";
      setTurns(prev => prev.map(t => t.id === turnId ? { ...t, error: message } : t));
    } finally {
      setIsAsking(false);
    }
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>

      {/* 성향 설정 오버레이 */}
      {showProfile && <ProfileSettings onClose={() => setShowProfile(false)} />}

      {/* 탭 바 — iOS 세그먼트 컨트롤 */}
      <div style={{
        padding: "10px 16px 8px",
        flexShrink: 0,
        background: "var(--bg)",
        borderBottom: "0.5px solid var(--sep)",
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <div style={{
          flex: 1,
          display: "flex",
          background: "var(--surface3)",
          borderRadius: 11,
          padding: 2,
        }}>
          {([["briefing", "AI 브리핑"], ["news", "뉴스"], ["chat", "채팅"], ["factcheck", "팩트체크"]] as [Tab, string][]).map(([tab, label]) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                flex: 1,
                padding: "6px 4px",
                fontSize: 12,
                fontWeight: activeTab === tab ? 700 : 500,
                color: activeTab === tab ? "white" : "var(--label2)",
                background: activeTab === tab ? "var(--primary)" : "transparent",
                borderRadius: 9,
                boxShadow: activeTab === tab ? "0 2px 8px rgba(0,122,255,0.28)" : "none",
                transition: "all 0.18s",
                letterSpacing: "-0.01em",
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          onClick={() => setShowProfile(true)}
          title="투자 성향 설정"
          style={{
            width: 32, height: 32, borderRadius: 10,
            background: "var(--surface)",
            border: "0.5px solid var(--sep)",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--label2)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
      </div>

      {/* ── AI 브리핑 탭 ── */}
      {activeTab === "briefing" && (
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 16px 32px", WebkitOverflowScrolling: "touch" as const }}>
          {loadingBriefing ? (
            <BriefingSkeleton />
          ) : briefingError ? (
            <div style={{
              background: "var(--surface)", borderRadius: 20, padding: "24px 20px",
              boxShadow: "var(--shadow)", textAlign: "center",
            }}>
              <div style={{ fontSize: 13, color: "var(--label2)", marginBottom: 6 }}>브리핑 로드 실패</div>
              <div style={{ fontSize: 13, color: "var(--red)", marginBottom: 16, fontWeight: 600 }}>{briefingError}</div>
              <button
                onClick={() => loadBriefing()}
                style={{
                  padding: "10px 24px", borderRadius: 12,
                  background: "var(--primary)", color: "white", fontSize: 13, fontWeight: 700,
                }}
              >
                다시 시도
              </button>
            </div>
          ) : briefing && !briefing.sections ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "48px 24px", gap: 16 }}>
              <div style={{
                width: 56, height: 56, borderRadius: 18,
                background: "var(--surface2)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--label3)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 3v18h18" /><path d="M18 17V9" /><path d="M13 17V5" /><path d="M8 17v-3" />
                </svg>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: "var(--label)", marginBottom: 6 }}>포트폴리오가 비어있어요</div>
                <div style={{ fontSize: 13, color: "var(--label2)", lineHeight: 1.7 }}>
                  종목을 추가하면 AI가 보유 현황을<br />분석해서 브리핑을 제공해요
                </div>
              </div>
            </div>
          ) : briefing ? (
            <BriefingView briefing={briefing} onRefresh={() => loadBriefing(true)} refreshing={loadingBriefing} />
          ) : null}
        </div>
      )}

      {/* ── 뉴스 요약 탭 ── */}
      {activeTab === "news" && (
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 16px 32px", WebkitOverflowScrolling: "touch" as const }}>
          {loadingNews || generatingNews ? (
            <BriefingSkeleton />
          ) : premarketNews ? (
            <PremarketNewsView news={premarketNews} onRefresh={refreshNews} refreshing={generatingNews} />
          ) : (
            <div style={{ background: "var(--surface)", borderRadius: 20, padding: "28px 20px", boxShadow: "var(--shadow)", textAlign: "center" }}>
              <div style={{ fontSize: 28, marginBottom: 12 }}>📰</div>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>개장 전 뉴스 요약</div>
              <div style={{ fontSize: 13, color: "var(--label3)", lineHeight: 1.7, marginBottom: 20 }}>
                매일 오전 8:50에 자동으로 생성됩니다.<br />오늘 요약이 아직 준비되지 않았어요.
              </div>
              <button
                onClick={refreshNews}
                style={{
                  padding: "11px 28px", borderRadius: 14,
                  background: "var(--primary)", color: "white",
                  fontSize: 14, fontWeight: 700,
                  boxShadow: "0 4px 12px rgba(0,122,255,0.28)",
                }}
              >
                지금 생성하기
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── 팩트체크 탭 ── */}
      {activeTab === "factcheck" && <UploadCard />}

      {/* ── 채팅 탭 ── */}
      {activeTab === "chat" && (
        <>
          <div style={{
            flex: 1, overflowY: "auto", padding: "16px 20px",
            display: "flex", flexDirection: "column", gap: 14,
            WebkitOverflowScrolling: "touch" as const,
          }}>
            {turns.length === 0 && (
              <div style={{
                flex: 1, display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center", gap: 20, padding: "0 20px",
              }}>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 16, color: "var(--label)", fontWeight: 800, letterSpacing: "-0.03em", marginBottom: 5 }}>무엇이든 물어보세요</div>
                  <div style={{ fontSize: 12, color: "var(--label2)", lineHeight: 1.8 }}>
                    업로드한 자료 · 포트폴리오 · 공시 기반으로 답변
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 7, width: "100%", maxWidth: 320 }}>
                  {[
                    "오늘 포트폴리오 전반 요약해줘",
                    "최근 공시에서 주목할 내용 있어?",
                    "내 포트폴리오 리스크 분석해줘",
                    "가장 많이 오른 종목 이유는?",
                  ].map(q => (
                    <button
                      key={q}
                      onClick={() => { setInput(q); }}
                      style={{
                        fontSize: 13, fontWeight: 500,
                        color: "var(--label)",
                        background: "var(--surface)",
                        border: "0.5px solid var(--sep)",
                        borderRadius: 12, padding: "10px 14px",
                        textAlign: "left",
                        boxShadow: "var(--shadow-sm)",
                        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
                      }}
                    >
                      <span>{q}</span>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--label3)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M9 18l6-6-6-6" />
                      </svg>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {turns.map(turn => (
              <ChatTurnView key={turn.id} turn={turn} />
            ))}
            <div ref={bottomRef} />
          </div>

          {/* 입력창 */}
          <div style={{
            padding: "8px 12px 12px",
            borderTop: "0.5px solid var(--sep)",
            flexShrink: 0,
            display: "flex", gap: 8, alignItems: "flex-end",
            background: "var(--bg)",
          }}>
            <div style={{
              flex: 1,
              display: "flex", alignItems: "center",
              background: "var(--surface)",
              borderRadius: 24,
              padding: "0 16px",
              minHeight: 44,
              border: "0.5px solid var(--sep)",
              boxShadow: "var(--shadow-sm)",
            }}>
              <input
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !isAsking) send(); }}
                placeholder="메시지를 입력하세요"
                disabled={isAsking}
                style={{
                  flex: 1, background: "transparent",
                  fontSize: 14, border: "none", color: "var(--label)",
                  padding: "10px 0",
                }}
              />
            </div>
            <button
              onClick={send}
              disabled={isAsking || !input.trim()}
              style={{
                width: 44, height: 44, borderRadius: "50%",
                background: isAsking || !input.trim() ? "var(--surface2)" : "var(--primary)",
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0,
                transition: "all 0.18s",
                boxShadow: isAsking || !input.trim() ? "none" : "0 4px 12px rgba(0,122,255,0.30)",
              }}
            >
              {isAsking ? (
                <div style={{
                  width: 15, height: 15,
                  border: "2px solid var(--label3)", borderTopColor: "var(--label)",
                  borderRadius: "50%", animation: "spin 0.75s linear infinite",
                }} />
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                  <path d="M12 4L12 20M12 4L6 10M12 4L18 10" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ─── 브리핑 뷰 ───────────────────────────────────────────────────────────────

const SENTIMENT_CONFIG = {
  positive: { label: "긍정적", color: "var(--red)", bg: "rgba(255,59,48,0.07)", dot: "#FF3B30" },
  negative: { label: "부정적", color: "var(--primary)", bg: "rgba(0,122,255,0.07)", dot: "#007AFF" },
  neutral:  { label: "중립",   color: "var(--label3)", bg: "var(--surface2)",      dot: "#AEAEB2" },
};

function StatsBar({ stats }: { stats: PortfolioStats }) {
  const isProfit = stats.total_pnl_pct >= 0;
  const color = isProfit ? "var(--red)" : "var(--primary)";
  return (
    <div style={{
      display: "flex", gap: 0,
      background: "var(--surface3)", borderRadius: 14,
      overflow: "hidden", marginBottom: 16,
    }}>
      <div style={{ flex: 1, padding: "10px 14px", textAlign: "center", borderRight: "0.5px solid var(--sep)" }}>
        <div style={{ fontSize: 11, color: "var(--label2)", fontWeight: 600, marginBottom: 3 }}>평가손익</div>
        <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.04em", color }}>
          {stats.total_pnl_pct > 0 ? "+" : ""}{stats.total_pnl_pct.toFixed(2)}%
        </div>
      </div>
      <div style={{ flex: 1, padding: "10px 14px", textAlign: "center", borderRight: "0.5px solid var(--sep)" }}>
        <div style={{ fontSize: 11, color: "var(--label2)", fontWeight: 600, marginBottom: 3 }}>최고</div>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--red)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {stats.best.corp_name}
        </div>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--red)" }}>
          {stats.best.pnl_pct > 0 ? "+" : ""}{stats.best.pnl_pct.toFixed(1)}%
        </div>
      </div>
      <div style={{ flex: 1, padding: "10px 14px", textAlign: "center" }}>
        <div style={{ fontSize: 11, color: "var(--label2)", fontWeight: 600, marginBottom: 3 }}>최저</div>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {stats.worst.corp_name}
        </div>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--primary)" }}>
          {stats.worst.pnl_pct > 0 ? "+" : ""}{stats.worst.pnl_pct.toFixed(1)}%
        </div>
      </div>
    </div>
  );
}

function BriefingView({ briefing, onRefresh, refreshing }: {
  briefing: PortfolioBriefing;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const s = briefing.sections;
  const sentiment = s?.sentiment ?? "neutral";
  const sentCfg = SENTIMENT_CONFIG[sentiment] ?? SENTIMENT_CONFIG.neutral;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>

      {/* ── 헤더 카드 ── */}
      <div style={{ background: "var(--surface)", borderRadius: 20, overflow: "hidden", boxShadow: "var(--shadow)" }}>
        <div style={{
          padding: "14px 18px 13px",
          background: sentCfg.bg,
          borderBottom: "0.5px solid var(--sep)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: sentCfg.dot }} />
            <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: "-0.03em" }}>AI 브리핑</span>
            <span style={{
              fontSize: 10, fontWeight: 700, color: sentCfg.color,
              background: `${sentCfg.dot}20`, borderRadius: 6, padding: "2px 7px",
            }}>
              {sentCfg.label}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, color: "var(--label3)" }}>{briefing.generated_at}</span>
            <button
              onClick={onRefresh}
              disabled={refreshing}
              style={{
                fontSize: 11, color: "var(--primary)", fontWeight: 700,
                padding: "5px 12px", background: "rgba(0,122,255,0.09)", borderRadius: 9,
              }}
            >
              {refreshing ? "…" : "새로고침"}
            </button>
          </div>
        </div>

        <div style={{ padding: "14px 18px 16px" }}>
          {/* 포트폴리오 스냅샷 */}
          {briefing.portfolio_stats && <StatsBar stats={briefing.portfolio_stats} />}

          {s ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {/* 요약 */}
              <p style={{ fontSize: 14, color: "var(--label)", lineHeight: 1.85, margin: 0 }}>
                {s.summary}
              </p>

              {/* 종목 하이라이트 */}
              {s.highlights.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {s.highlights.map((h, i) => {
                    const isUp = h.status === "상승";
                    const isDown = h.status === "하락";
                    const color = isUp ? "var(--red)" : isDown ? "var(--primary)" : "var(--label3)";
                    return (
                      <div key={i} style={{
                        borderRadius: 12, padding: "11px 14px",
                        background: "var(--surface3)",
                        borderLeft: `3px solid ${color}`,
                        display: "flex", flexDirection: "column", gap: 4,
                      }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                          <span style={{ fontSize: 12, fontWeight: 800, color }}>{h.corp_name}</span>
                          {h.change_note && (
                            <span style={{
                              fontSize: 10, fontWeight: 700, color,
                              background: isUp ? "rgba(255,59,48,0.1)" : isDown ? "rgba(0,122,255,0.1)" : "var(--surface2)",
                              borderRadius: 5, padding: "1px 6px",
                            }}>
                              {h.change_note}
                            </span>
                          )}
                          <span style={{
                            fontSize: 11, fontWeight: 600, color: "var(--label2)",
                            marginLeft: "auto",
                          }}>
                            {h.status}
                          </span>
                        </div>
                        <p style={{ fontSize: 13, color: "var(--label)", lineHeight: 1.65, margin: 0 }}>{h.note}</p>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* 액션 체크리스트 */}
              {s.action_items && s.action_items.length > 0 && (
                <div style={{
                  background: "rgba(0,122,255,0.04)", borderRadius: 14, padding: "12px 14px",
                  border: "0.5px solid rgba(0,122,255,0.12)",
                }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "var(--primary)", marginBottom: 8, letterSpacing: "0.03em" }}>오늘 확인 체크리스트</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                    {s.action_items.map((item, i) => (
                      <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                        <div style={{
                          width: 18, height: 18, borderRadius: 6, border: "1.5px solid rgba(0,122,255,0.35)",
                          flexShrink: 0, marginTop: 1, display: "flex", alignItems: "center", justifyContent: "center",
                        }}>
                          <span style={{ fontSize: 10, color: "var(--primary)", fontWeight: 700 }}>{i + 1}</span>
                        </div>
                        <p style={{ fontSize: 13, color: "var(--label)", lineHeight: 1.6, margin: 0 }}>{item}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 오늘 체크 + 리스크 */}
              <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "0.5px solid var(--sep)", paddingTop: 12 }}>
                {s.watch && (
                  <div style={{ display: "flex", gap: 8 }}>
                    <div style={{
                      fontSize: 9, fontWeight: 700, color: "white",
                      background: "var(--primary)", borderRadius: 5,
                      padding: "2px 6px", flexShrink: 0, alignSelf: "flex-start", marginTop: 2, letterSpacing: "0.02em",
                    }}>체크</div>
                    <p style={{ fontSize: 13, color: "var(--label)", lineHeight: 1.7, margin: 0 }}>{s.watch}</p>
                  </div>
                )}
                {s.risk && (
                  <div style={{ display: "flex", gap: 8 }}>
                    <div style={{
                      fontSize: 9, fontWeight: 700, color: "white",
                      background: "var(--orange)", borderRadius: 5,
                      padding: "2px 6px", flexShrink: 0, alignSelf: "flex-start", marginTop: 2, letterSpacing: "0.02em",
                    }}>리스크</div>
                    <p style={{ fontSize: 13, color: "var(--label2)", lineHeight: 1.7, margin: 0 }}>{s.risk}</p>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <p style={{ fontSize: 14, color: "var(--label)", lineHeight: 1.85, margin: 0, whiteSpace: "pre-wrap" }}>
              {briefing.briefing}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function BriefingSkeleton() {
  return (
    <div style={{ background: "var(--surface)", borderRadius: 20, padding: "20px", boxShadow: "var(--shadow)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <div style={{ width: 80, height: 18, borderRadius: 6, background: "var(--bg)", animation: "pulse 1.4s ease-in-out infinite", marginBottom: 6 }} />
          <div style={{ width: 120, height: 12, borderRadius: 5, background: "var(--bg)", animation: "pulse 1.4s ease-in-out infinite" }} />
        </div>
        <div style={{ width: 60, height: 28, borderRadius: 10, background: "var(--bg)", animation: "pulse 1.4s ease-in-out infinite" }} />
      </div>
      {[100, 96, 90, 74, 82, 68].map((w, i) => (
        <div key={i} style={{
          width: `${w}%`, height: 14, borderRadius: 5, background: "var(--bg)",
          animation: "pulse 1.4s ease-in-out infinite",
          marginBottom: i < 5 ? 9 : 0,
          animationDelay: `${i * 0.08}s`,
        }} />
      ))}
    </div>
  );
}

function renderFormattedText(text: string): React.ReactNode {
  const lines = text.split("\n");
  const result: React.ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("- ") || line.startsWith("• ")) {
      const bullets: string[] = [];
      while (i < lines.length && (lines[i].startsWith("- ") || lines[i].startsWith("• "))) {
        bullets.push(lines[i].slice(2));
        i++;
      }
      result.push(
        <ul key={i} style={{ margin: "4px 0", paddingLeft: 18, display: "flex", flexDirection: "column", gap: 3 }}>
          {bullets.map((b, bi) => (
            <li key={bi} style={{ fontSize: 14, lineHeight: 1.6 }}>{renderInline(b)}</li>
          ))}
        </ul>
      );
    } else if (line.trim() === "") {
      result.push(<div key={i} style={{ height: 6 }} />);
      i++;
    } else {
      result.push(<p key={i} style={{ margin: 0, lineHeight: 1.65 }}>{renderInline(line)}</p>);
      i++;
    }
  }
  return <>{result}</>;
}

function renderInline(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} style={{ fontWeight: 700 }}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function ChatTurnView({ turn }: { turn: ChatTurn }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, animation: "fadeIn 0.2s ease-out" }}>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <div style={{
          background: "var(--primary)", color: "white",
          borderRadius: "20px 20px 5px 20px",
          padding: "10px 15px", maxWidth: "80%",
          fontSize: 14, lineHeight: 1.55, whiteSpace: "pre-wrap", wordBreak: "break-word",
          boxShadow: "0 2px 8px rgba(0,122,255,0.25)",
        }}>
          {turn.question}
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 9,
          background: "var(--primary)",
          flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 9, fontWeight: 800, color: "white",
          letterSpacing: "0.01em",
        }}>
          AI
        </div>
        <div style={{
          background: "var(--surface)", color: "var(--label)",
          borderRadius: "20px 20px 20px 5px",
          padding: "11px 15px", maxWidth: "80%",
          fontSize: 14, wordBreak: "break-word", lineHeight: 1.6,
          boxShadow: "var(--shadow-sm)",
          border: "0.5px solid var(--sep)",
        }}>
          {turn.error ? (
            <span style={{ color: "var(--red)" }}>{turn.error}</span>
          ) : turn.answer ? (
            renderFormattedText(turn.answer)
          ) : (
            <TypingIndicator />
          )}
        </div>
      </div>

      {(turn.sources.length > 0 || turn.companies_synced.length > 0) && (
        <div style={{ marginLeft: 34, display: "flex", flexDirection: "column", gap: 6 }}>
          {turn.companies_synced.length > 0 && (
            <SyncedBadge companies={turn.companies_synced} />
          )}
          {turn.sources.length > 0 && (
            <SourceBadges sources={turn.sources} />
          )}
        </div>
      )}
    </div>
  );
}

function SourceBadges({ sources }: { sources: Source[] }) {
  const [expanded, setExpanded] = React.useState(false);
  const shown = expanded ? sources : sources.slice(0, 2);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <button
        onClick={() => setExpanded(v => !v)}
        style={{
          display: "flex", alignItems: "center", gap: 5,
          fontSize: 11, color: "var(--label2)", fontWeight: 600, alignSelf: "flex-start",
        }}
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
          <path d="M9 19h6M12 15V5M8 9l4-4 4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        참고 자료 {sources.length}건 {expanded ? "▲" : "▼"}
      </button>
      {expanded && shown.map((s, i) => (
        <div key={i} style={{
          background: "var(--surface)", borderRadius: 10, padding: "8px 11px",
          fontSize: 12, color: "var(--label2)", lineHeight: 1.5,
          border: "0.5px solid var(--sep)",
        }}>
          <div style={{
            overflow: "hidden", display: "-webkit-box",
            WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
          }}>
            {s.snippet}
          </div>
          <div style={{ fontSize: 11, color: "var(--label2)", marginTop: 3 }}>{s.label}</div>
        </div>
      ))}
    </div>
  );
}

function SyncedBadge({ companies }: { companies: CompanySynced[] }) {
  return (
    <div style={{
      marginLeft: 34,
      display: "inline-flex", alignItems: "center", gap: 6,
      fontSize: 12, color: "var(--primary)",
      background: "rgba(0,122,255,0.08)",
      borderRadius: 100, padding: "3px 10px", alignSelf: "flex-start",
    }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--primary)", display: "inline-block" }} />
      {companies.map(c => c.corp_name).join(" · ")} 공시 자동 수집
    </div>
  );
}

function TypingIndicator() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "2px 0" }}>
      {[0, 1, 2].map(i => (
        <div key={i} style={{
          width: 7, height: 7, borderRadius: "50%", background: "var(--label2)",
          animation: `bounce 1.2s ease-in-out ${i * 0.2}s infinite`,
        }} />
      ))}
      <style>{`@keyframes bounce { 0%,60%,100%{transform:translateY(0);opacity:.4} 30%{transform:translateY(-5px);opacity:1} }`}</style>
    </div>
  );
}

const NEWS_TONE = {
  positive: { color: "var(--red)",    bg: "rgba(255,59,48,0.08)",  label: "긍정" },
  negative: { color: "var(--primary)", bg: "rgba(0,122,255,0.08)", label: "부정" },
  neutral:  { color: "var(--label3)", bg: "var(--surface2)",        label: "중립" },
};

function PremarketNewsView({ news, onRefresh, refreshing }: {
  news: PremarketNews;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const s = news.sections;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ background: "var(--surface)", borderRadius: 20, overflow: "hidden", boxShadow: "var(--shadow)" }}>
        <div style={{
          padding: "14px 18px 13px",
          background: "rgba(255,149,0,0.06)",
          borderBottom: "0.5px solid var(--sep)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--orange)" }} />
            <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: "-0.03em" }}>개장 전 뉴스 요약</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, color: "var(--label3)" }}>{news.generated_at}</span>
            <button
              onClick={onRefresh}
              disabled={refreshing}
              style={{
                fontSize: 11, color: "var(--primary)", fontWeight: 700,
                padding: "5px 12px", background: "rgba(0,122,255,0.09)", borderRadius: 9,
              }}
            >
              {refreshing ? "…" : "새로고침"}
            </button>
          </div>
        </div>

        <div style={{ padding: "14px 18px 16px", display: "flex", flexDirection: "column", gap: 14 }}>
          {s ? (
            <>
              <p style={{ fontSize: 14, fontWeight: 700, color: "var(--label)", margin: 0, letterSpacing: "-0.02em", lineHeight: 1.5 }}>
                {s.headline}
              </p>

              {s.items.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {s.items.map((item, i) => {
                    const tone = NEWS_TONE[item.tone] ?? NEWS_TONE.neutral;
                    return (
                      <div key={i} style={{
                        borderRadius: 12, padding: "10px 13px",
                        background: tone.bg,
                        borderLeft: `3px solid ${tone.color}`,
                        display: "flex", flexDirection: "column", gap: 3,
                      }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                          <span style={{ fontSize: 12, fontWeight: 800, color: tone.color }}>{item.corp_name}</span>
                          <span style={{ fontSize: 9, fontWeight: 700, color: tone.color, background: `${tone.color}20`, borderRadius: 5, padding: "1px 6px" }}>
                            {tone.label}
                          </span>
                        </div>
                        <p style={{ fontSize: 13, color: "var(--label)", lineHeight: 1.65, margin: 0 }}>{item.summary}</p>
                      </div>
                    );
                  })}
                </div>
              )}

              {s.market_outlook && (
                <div style={{ display: "flex", gap: 8, borderTop: "0.5px solid var(--sep)", paddingTop: 12 }}>
                  <div style={{ fontSize: 9, fontWeight: 700, color: "white", background: "var(--orange)", borderRadius: 5, padding: "2px 6px", flexShrink: 0, alignSelf: "flex-start", marginTop: 2, letterSpacing: "0.02em" }}>
                    전망
                  </div>
                  <p style={{ fontSize: 13, color: "var(--label2)", lineHeight: 1.7, margin: 0 }}>{s.market_outlook}</p>
                </div>
              )}
            </>
          ) : (
            <p style={{ fontSize: 13, color: "var(--label)", lineHeight: 1.85, margin: 0, whiteSpace: "pre-wrap" }}>{news.summary}</p>
          )}
        </div>
      </div>
    </div>
  );
}

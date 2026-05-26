"use client";

import { useEffect, useState } from "react";
import { useSession, signOut } from "next-auth/react";
import { useRouter } from "next/navigation";

import { ChatCard } from "../components/ChatCard";
import { PortfolioCard } from "../components/PortfolioCard";
import { fetchAlerts, fetchMarketIndices, markAlertsRead, initAuth } from "../lib/api";
import type { PriceAlert } from "../lib/api";
import type { MarketIndex, MarketStatus } from "../lib/types";

type MobilePanel = 0 | 1;

function getInitialTheme(): "light" | "dark" | "system" {
  if (typeof window === "undefined") return "system";
  const t = localStorage.getItem("theme");
  if (t === "dark" || t === "light") return t;
  return "system";
}

export default function Home() {
  const { data: session, status } = useSession();
  const router = useRouter();

  const [authReady, setAuthReady] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark" | "system">("system");

  useEffect(() => {
    setTheme(getInitialTheme());
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
  }

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
    if (status === "authenticated") initAuth().then(() => setAuthReady(true));
  }, [status, router]);
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>(1);
  const [indices, setIndices] = useState<Record<string, MarketIndex>>({});
  const [marketStatus, setMarketStatus] = useState<MarketStatus | null>(null);
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [showAlerts, setShowAlerts] = useState(false);
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const [portfolioVersion, setPortfolioVersion] = useState(0);
  const [indicesLoaded, setIndicesLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await fetchMarketIndices();
        if (!cancelled) {
          setIndices(data.indices);
          setMarketStatus(data.market_status);
        }
      } catch { /* 시장 조회 실패 무시 */ }
      finally { if (!cancelled) setIndicesLoaded(true); }
    }
    load();
    const id = setInterval(load, 60_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // 알림 폴링 (2분마다)
  useEffect(() => {
    let cancelled = false;
    async function loadAlerts() {
      try {
        const data = await fetchAlerts();
        if (!cancelled) setAlerts(data);
      } catch { /* 무시 */ }
    }
    loadAlerts();
    const id = setInterval(loadAlerts, 2 * 60_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (status === "loading" || status === "unauthenticated" || !authReady) {
    return (
      <div style={{ minHeight: "100dvh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg)" }}>
        <div style={{ fontSize: 13, color: "var(--label2)" }}>로딩 중…</div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100dvh", background: "var(--bg)" }}>

      {/* 글로벌 헤더 */}
      <header style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 20px",
        height: 52,
        background: "var(--header-bg)",
        backdropFilter: "blur(28px)",
        WebkitBackdropFilter: "blur(28px)",
        borderBottom: "0.5px solid var(--sep)",
        flexShrink: 0,
        zIndex: 10,
        gap: 16,
      }}>
        {/* 로고 + 장 상태 */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          <img src="/compass1.png" alt="주식나침반" style={{ width: 28, height: 28, borderRadius: 7, display: "block" }} />
          <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: "-0.04em" }}>주식나침반</span>
          {marketStatus && <MarketStatusBadge status={marketStatus} />}
        </div>

        {/* 시장 지수 */}
        <div className="market-badges" style={{ display: "flex", gap: 6, flex: 1, justifyContent: "center", alignItems: "center" }}>
          {Object.values(indices).map((idx, i) => (
            <MarketBadge key={idx.name} index={idx} className={`market-badge market-badge--${i}`} />
          ))}
          {Object.keys(indices).length === 0 && !indicesLoaded && (
            <div style={{ fontSize: 12, color: "var(--label3)" }}>시장 조회 중…</div>
          )}
        </div>

        {/* 알림 + 유저 + 백엔드 상태 */}
        <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <AlertBell alerts={alerts} show={showAlerts} onToggle={() => setShowAlerts(v => !v)} />
          <button
            onClick={toggleTheme}
            title={theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
            style={{
              width: 36, height: 36, borderRadius: 10,
              background: "transparent",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "var(--label3)",
              transition: "color 0.15s",
            }}
          >
            {theme === "dark" ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="5" />
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </button>
          {session?.user?.image && (
            <div style={{ position: "relative" }}>
              <img
                src={session.user.image}
                alt="프로필"
                onClick={() => setShowProfileMenu(v => !v)}
                style={{ width: 28, height: 28, borderRadius: "50%", cursor: "pointer", border: "1.5px solid var(--sep)", display: "block" }}
              />
              {showProfileMenu && (
                <>
                  <div onClick={() => setShowProfileMenu(false)} style={{ position: "fixed", inset: 0, zIndex: 19 }} />
                  <div style={{
                    position: "absolute", top: 36, right: 0, zIndex: 20,
                    background: "var(--surface)", borderRadius: 14,
                    boxShadow: "0 8px 32px rgba(0,0,0,0.15)",
                    border: "0.5px solid var(--sep)", minWidth: 180, overflow: "hidden",
                  }}>
                    <div style={{ padding: "12px 16px", borderBottom: "0.5px solid var(--sep)" }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "var(--label)" }}>{session.user.name}</div>
                      <div style={{ fontSize: 11, color: "var(--label3)", marginTop: 2 }}>{session.user.email}</div>
                    </div>
                    <button
                      onClick={() => { setShowProfileMenu(false); signOut({ callbackUrl: "/login" }); }}
                      style={{
                        width: "100%", padding: "12px 16px", textAlign: "left",
                        fontSize: 13, fontWeight: 600, color: "var(--red)",
                        background: "transparent", cursor: "pointer",
                      }}
                    >
                      로그아웃
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </header>
      {showAlerts && alerts.length > 0 && (
        <AlertDropdown alerts={alerts} onClose={() => setShowAlerts(false)} onReadAll={async () => { const ids = alerts.map(a => a.id); await markAlertsRead(ids); setAlerts([]); setShowAlerts(false); }} />
      )}

      {/* 메인 대시보드 그리드 */}
      <div className="dashboard-grid">

        {/* ── 왼쪽: 내 지갑 ── */}
        <div className={`dashboard-panel dashboard-panel--highlight ${mobilePanel === 0 ? "dashboard-panel--active" : ""}`}>
          <PanelHeader title="내 지갑" subtitle="보유 종목 · 관심종목 · 배분" />
          <PortfolioCard onPortfolioChange={() => setPortfolioVersion(v => v + 1)} />
        </div>

        {/* ── 오른쪽: AI 비서 ── */}
        <div className={`dashboard-panel ${mobilePanel === 1 ? "dashboard-panel--active" : ""}`}>
          <PanelHeader title="AI 비서" subtitle="브리핑 · 채팅 · 팩트체크" />
          <ChatCard portfolioVersion={portfolioVersion} />
        </div>

      </div>

      {/* 모바일 하단 탭바 */}
      <nav className="mobile-tab-bar">
        <button
          className={mobilePanel === 0 ? "active" : ""}
          onClick={() => setMobilePanel(0)}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
          지갑
        </button>
        <button
          className={mobilePanel === 1 ? "active" : ""}
          onClick={() => setMobilePanel(1)}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          AI
        </button>
      </nav>
    </div>
  );
}

const MARKET_STATUS_STYLE: Record<string, { color: string; bg: string; dot: string }> = {
  open:   { color: "#34C759", bg: "rgba(52,199,89,0.1)",   dot: "#34C759" },
  pre:    { color: "#FF9500", bg: "rgba(255,149,0,0.1)",   dot: "#FF9500" },
  closed: { color: "var(--label3)", bg: "var(--surface2)", dot: "#AEAEB2" },
};

function MarketStatusBadge({ status }: { status: MarketStatus }) {
  const s = MARKET_STATUS_STYLE[status.status] ?? MARKET_STATUS_STYLE.closed;
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 5,
      background: s.bg, borderRadius: 20, padding: "4px 10px",
      border: `0.5px solid ${s.dot}30`,
    }}>
      <span style={{
        width: 5, height: 5, borderRadius: "50%", background: s.dot,
        boxShadow: status.status === "open" ? `0 0 0 2.5px ${s.dot}40` : "none",
        flexShrink: 0,
      }} />
      <span style={{ fontSize: 11, fontWeight: 700, color: s.color, letterSpacing: "-0.01em" }}>{status.label}</span>
    </div>
  );
}

function MarketBadge({ index, className }: { index: MarketIndex; className?: string }) {
  const up = index.change_pct >= 0;
  const color = up ? "var(--red)" : "var(--primary)";
  const sign = up ? "+" : "";
  return (
    <div className={className} style={{
      display: "flex", alignItems: "center", gap: 6,
      background: "var(--surface2)",
      borderRadius: 20, padding: "4px 10px",
    }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--label3)" }}>{index.name}</span>
      <span style={{ fontSize: 12, fontWeight: 800, color, letterSpacing: "-0.03em" }}>
        {index.value.toLocaleString("ko-KR")}
      </span>
      <span style={{ fontSize: 10, fontWeight: 700, color }}>
        {sign}{index.change_pct.toFixed(2)}%
      </span>
    </div>
  );
}

function PanelHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div style={{
      padding: "13px 20px 12px",
      borderBottom: "0.5px solid var(--sep)",
      flexShrink: 0,
      display: "flex", alignItems: "center", justifyContent: "space-between",
    }}>
      <div style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.04em" }}>{title}</div>
      <div style={{ fontSize: 11, color: "var(--label3)", fontWeight: 500, letterSpacing: "0" }}>{subtitle}</div>
    </div>
  );
}

function AlertBell({ alerts, show, onToggle }: {
  alerts: PriceAlert[];
  show: boolean;
  onToggle: () => void;
}) {
  const count = alerts.length;
  return (
    <button
      onClick={onToggle}
      style={{ position: "relative", width: 36, height: 36, borderRadius: 10, background: show ? "rgba(0,122,255,0.1)" : "transparent", display: "flex", alignItems: "center", justifyContent: "center" }}
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={count > 0 ? "var(--orange)" : "var(--label3)"} strokeWidth="2" strokeLinecap="round">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
      {count > 0 && (
        <div style={{
          position: "absolute", top: 3, right: 3,
          minWidth: 15, height: 15, borderRadius: 8,
          background: "var(--red)", color: "white",
          fontSize: 9, fontWeight: 800,
          display: "flex", alignItems: "center", justifyContent: "center",
          padding: "0 3px",
          border: "1.5px solid var(--bg)",
        }}>
          {count > 9 ? "9+" : count}
        </div>
      )}
    </button>
  );
}

function AlertDropdown({ alerts, onClose, onReadAll }: {
  alerts: PriceAlert[];
  onClose: () => void;
  onReadAll: () => void;
}) {
  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 19 }} />
      <div style={{
        position: "fixed", top: 56, right: 12, zIndex: 20,
        background: "var(--surface)", borderRadius: 16,
        boxShadow: "0 8px 32px rgba(0,0,0,0.15)", width: 320,
        overflow: "hidden", border: "0.5px solid var(--sep)",
      }}>
        <div style={{ padding: "13px 16px 11px", borderBottom: "0.5px solid var(--sep)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 14, fontWeight: 700 }}>가격 알림 {alerts.length}건</span>
          <button onClick={onReadAll} style={{ fontSize: 12, color: "var(--primary)", fontWeight: 600 }}>모두 읽음</button>
        </div>
        <div style={{ maxHeight: 320, overflowY: "auto" }}>
          {alerts.map((a, i) => (
            <div key={a.id}>
              {i > 0 && <div style={{ height: "0.5px", background: "var(--sep)", marginLeft: 16 }} />}
              <div style={{ padding: "12px 16px", display: "flex", gap: 10, alignItems: "flex-start" }}>
                <div style={{
                  width: 8, height: 8, borderRadius: "50%", marginTop: 5, flexShrink: 0,
                  background: a.type === "target" ? "var(--red)" : "var(--primary)",
                }} />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: a.type === "target" ? "var(--red)" : "var(--primary)" }}>
                    {a.type === "target" ? "목표가 도달" : "손절가 도달"}
                  </div>
                  <div style={{ fontSize: 13, color: "var(--label)", marginTop: 2, lineHeight: 1.5 }}>{a.message}</div>
                  <div style={{ fontSize: 11, color: "var(--label3)", marginTop: 3 }}>
                    {new Date(a.created_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

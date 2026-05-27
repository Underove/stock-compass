"use client";

import { signIn } from "next-auth/react";

export default function LoginPage() {
  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "var(--bg)", padding: 24,
    }}>
      <div style={{
        width: "100%", maxWidth: 360, background: "var(--surface)",
        borderRadius: 24, padding: 40, boxShadow: "var(--shadow-md)",
        display: "flex", flexDirection: "column", alignItems: "center", gap: 24,
      }}>
        <div style={{ textAlign: "center" }}>
          <img src="/nova.png" alt="NOVA" style={{ width: 72, height: 72, borderRadius: 18, marginBottom: 14, display: "block", margin: "0 auto 14px" }} />
          <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: "0.08em" }}>N.O.V.A</div>
          <div style={{ fontSize: 13, color: "var(--label2)", marginTop: 6 }}>
            AI 기반 투자 인사이트 플랫폼
          </div>
        </div>

        <button
          onClick={() => signIn("google", { callbackUrl: "/" })}
          style={{
            width: "100%", display: "flex", alignItems: "center", justifyContent: "center",
            gap: 12, padding: "14px 20px", borderRadius: 14,
            border: "1.5px solid var(--sep)", background: "var(--surface)",
            fontSize: 16, fontWeight: 700, cursor: "pointer", color: "var(--label)",
            boxShadow: "var(--shadow-sm)", transition: "box-shadow 0.15s",
            letterSpacing: "-0.015em",
          }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Google로 시작하기
        </button>

        <p style={{ fontSize: 11, color: "var(--label3)", textAlign: "center" }}>
          로그인하면 포트폴리오가 계정에 안전하게 저장돼요
        </p>
      </div>
    </div>
  );
}

"use client";

import { AlertCircle, CheckCircle2, Info } from "lucide-react";
import { useToasts } from "../hooks/useToast";

const CFG = {
  success: { Icon: CheckCircle2, color: "var(--green)", bg: "rgba(52,199,89,0.16)" },
  error:   { Icon: AlertCircle,  color: "var(--red)",   bg: "rgba(255,59,48,0.16)" },
  info:    { Icon: Info,         color: "var(--primary)", bg: "rgba(0,122,255,0.16)" },
};

export function ToastHost() {
  const toasts = useToasts();
  if (toasts.length === 0) return null;
  return (
    <div style={{
      position: "fixed", bottom: 24, left: 0, right: 0,
      display: "flex", flexDirection: "column", alignItems: "center", gap: 8,
      zIndex: 9999, pointerEvents: "none", padding: "0 16px",
    }}>
      {toasts.map(t => {
        const c = CFG[t.type];
        const Icon = c.Icon;
        return (
          <div
            key={t.id}
            className="modal-enter"
            style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "10px 16px 10px 12px",
              background: "var(--surface)", color: "var(--label)",
              borderRadius: 100, boxShadow: "0 4px 18px rgba(0,0,0,0.16)",
              border: "0.5px solid var(--sep)",
              fontSize: 14, fontWeight: 600, letterSpacing: "-0.015em",
              maxWidth: 360,
            }}
          >
            <div style={{
              width: 22, height: 22, borderRadius: 11,
              background: c.bg, color: c.color,
              display: "flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0,
            }}>
              <Icon size={13} strokeWidth={2.6} />
            </div>
            <span>{t.message}</span>
          </div>
        );
      })}
    </div>
  );
}

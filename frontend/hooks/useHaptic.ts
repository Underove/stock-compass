"use client";

/**
 * Web Haptics API — Android Chrome 등에서 동작 (iOS Safari는 미지원).
 * 미지원 환경에선 silent no-op.
 *
 * 사용처: 종목 추가/삭제, 매매 기록, 알림 해제 등 확정성 액션
 */
export function haptic(kind: "light" | "medium" | "heavy" | "success" | "error" = "light") {
  if (typeof navigator === "undefined" || !("vibrate" in navigator)) return;
  const pattern =
    kind === "light"   ? 8 :
    kind === "medium"  ? 18 :
    kind === "heavy"   ? 30 :
    kind === "success" ? [12, 40, 18] :
                          [30, 40, 30]; // error
  try { navigator.vibrate(pattern); } catch { /* ignore */ }
}

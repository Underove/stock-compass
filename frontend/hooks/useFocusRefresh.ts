"use client";

import { useEffect, useRef } from "react";

/**
 * 앱이 포커스 복귀(visibilitychange)되면 콜백 실행. Toss는 백그라운드 후 복귀 시 잔액·시세 자동 갱신.
 *
 * - 마지막 갱신 후 minStaleMs 초과 시에만 호출 (과도한 호출 방지)
 * - 페이지 hidden → visible 전환 시 trigger
 */
export function useFocusRefresh(refresh: () => void, minStaleMs = 30_000) {
  const lastRunRef = useRef<number>(Date.now());
  useEffect(() => {
    const onVis = () => {
      if (document.visibilityState !== "visible") return;
      const now = Date.now();
      if (now - lastRunRef.current >= minStaleMs) {
        lastRunRef.current = now;
        refresh();
      }
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [refresh, minStaleMs]);
}

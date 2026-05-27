"use client";

import { useEffect, useRef, useState } from "react";

const THRESHOLD = 64;
const MAX_PULL = 96;

/**
 * 모바일 pull-to-refresh. scrollTop=0인 컨테이너에서 아래로 당기면 onRefresh 호출.
 *
 * Returns:
 *   ref       — 스크롤 컨테이너에 부착
 *   pullDist  — 현재 당겨진 픽셀 (0 ~ MAX_PULL)
 *   isRefreshing — onRefresh 진행 중
 */
export function usePullToRefresh<T extends HTMLElement>(onRefresh: () => Promise<void> | void) {
  const ref = useRef<T | null>(null);
  const startYRef = useRef<number | null>(null);
  const [pullDist, setPullDist] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const onTouchStart = (e: TouchEvent) => {
      if (el.scrollTop > 0 || isRefreshing) return;
      startYRef.current = e.touches[0].clientY;
    };

    const onTouchMove = (e: TouchEvent) => {
      if (startYRef.current === null || isRefreshing) return;
      const dy = e.touches[0].clientY - startYRef.current;
      if (dy > 0 && el.scrollTop === 0) {
        e.preventDefault();
        // 저항 곡선: dy^0.7 로 점차 둔화
        const eased = Math.min(MAX_PULL, Math.pow(dy, 0.85));
        setPullDist(eased);
      }
    };

    const onTouchEnd = async () => {
      if (startYRef.current === null) return;
      const reached = pullDist >= THRESHOLD;
      startYRef.current = null;
      if (reached) {
        setIsRefreshing(true);
        setPullDist(THRESHOLD);
        try { await onRefresh(); } catch { /* ignore */ }
        setIsRefreshing(false);
        setPullDist(0);
      } else {
        setPullDist(0);
      }
    };

    el.addEventListener("touchstart", onTouchStart, { passive: true });
    el.addEventListener("touchmove", onTouchMove, { passive: false });
    el.addEventListener("touchend", onTouchEnd);
    el.addEventListener("touchcancel", onTouchEnd);
    return () => {
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchmove", onTouchMove);
      el.removeEventListener("touchend", onTouchEnd);
      el.removeEventListener("touchcancel", onTouchEnd);
    };
  }, [onRefresh, isRefreshing, pullDist]);

  return { ref, pullDist, isRefreshing, threshold: THRESHOLD };
}

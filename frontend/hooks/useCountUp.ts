import { useEffect, useRef, useState } from "react";

/**
 * 숫자가 부드럽게 카운트업되는 훅. Toss 메인 잔액 같은 효과.
 *
 * - target 변화 시 ~600ms easeOutCubic으로 애니메이션
 * - 차이가 작거나(±0.1) 첫 마운트 시 즉시 표시
 * - prefers-reduced-motion 존중
 */
export function useCountUp(target: number, durationMs = 600): number {
  const [display, setDisplay] = useState(target);
  const fromRef = useRef(target);
  const startRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!isFinite(target)) {
      setDisplay(target);
      return;
    }
    const prefersReduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const from = fromRef.current;
    const diff = Math.abs(target - from);

    if (prefersReduced || diff < 0.1) {
      fromRef.current = target;
      setDisplay(target);
      return;
    }

    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    startRef.current = null;

    const tick = (ts: number) => {
      if (startRef.current === null) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const t = Math.min(1, elapsed / durationMs);
      // easeOutCubic
      const eased = 1 - Math.pow(1 - t, 3);
      const value = from + (target - from) * eased;
      setDisplay(value);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = target;
        rafRef.current = null;
      }
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [target, durationMs]);

  return display;
}

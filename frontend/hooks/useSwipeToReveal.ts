"use client";

import { useEffect, useRef, useState } from "react";

const REVEAL_WIDTH = 72;
const COMMIT_THRESHOLD = 36;

/**
 * 리스트 row 좌측 swipe → 우측 액션 버튼 노출.
 *
 * 사용:
 *   const { ref, offset, isOpen, close } = useSwipeToReveal<HTMLDivElement>();
 *   <div ref={ref} style={{ transform: `translateX(${-offset}px)` }}> ... </div>
 *   {isOpen && <button onClick={close}>...</button>}
 */
export function useSwipeToReveal<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [offset, setOffset] = useState(0);
  const [isOpen, setIsOpen] = useState(false);
  const startXRef = useRef<number | null>(null);
  const baseOffsetRef = useRef(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const onStart = (e: TouchEvent) => {
      startXRef.current = e.touches[0].clientX;
      baseOffsetRef.current = offset;
    };

    const onMove = (e: TouchEvent) => {
      if (startXRef.current === null) return;
      const dx = e.touches[0].clientX - startXRef.current;
      const next = Math.max(0, Math.min(REVEAL_WIDTH, baseOffsetRef.current - dx));
      setOffset(next);
    };

    const onEnd = () => {
      if (startXRef.current === null) return;
      startXRef.current = null;
      // 임계점 넘으면 fully open, 아니면 close
      const opening = offset > baseOffsetRef.current;
      const shouldOpen = opening
        ? offset >= COMMIT_THRESHOLD
        : offset >= REVEAL_WIDTH - COMMIT_THRESHOLD;
      setOffset(shouldOpen ? REVEAL_WIDTH : 0);
      setIsOpen(shouldOpen);
    };

    el.addEventListener("touchstart", onStart, { passive: true });
    el.addEventListener("touchmove", onMove, { passive: true });
    el.addEventListener("touchend", onEnd);
    el.addEventListener("touchcancel", onEnd);
    return () => {
      el.removeEventListener("touchstart", onStart);
      el.removeEventListener("touchmove", onMove);
      el.removeEventListener("touchend", onEnd);
      el.removeEventListener("touchcancel", onEnd);
    };
  }, [offset]);

  const close = () => { setOffset(0); setIsOpen(false); };
  return { ref, offset, isOpen, close, revealWidth: REVEAL_WIDTH };
}

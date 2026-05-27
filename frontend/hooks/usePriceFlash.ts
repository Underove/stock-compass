import { useEffect, useRef, useState } from "react";

export type PriceFlash = "up" | "down" | null;

/** 가격이 갱신될 때 'up' | 'down' 플래시 상태를 잠깐 반환. duration 후 자동 해제. */
export function usePriceFlash(
  price: number | null | undefined,
  durationMs = 600,
): PriceFlash {
  const prevRef = useRef<number | null | undefined>(price);
  const [flash, setFlash] = useState<PriceFlash>(null);

  useEffect(() => {
    const prev = prevRef.current;
    prevRef.current = price;
    if (prev == null || price == null || prev === price) return;
    setFlash(price > prev ? "up" : "down");
    const t = setTimeout(() => setFlash(null), durationMs);
    return () => clearTimeout(t);
  }, [price, durationMs]);

  return flash;
}

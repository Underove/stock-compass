"use client";

import { useEffect, useRef, useState } from "react";

import { API_BASE } from "../lib/api";

export type RealtimePrice = {
  stock_code: string;
  time: string;
  current_price: number;
  change_sign: string;
  change_amount: number;
  change_pct: number;
  volume: number;
};

export function isMarketOpen(): boolean {
  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const day = kst.getUTCDay();
  if (day === 0 || day === 6) return false;
  const total = kst.getUTCHours() * 60 + kst.getUTCMinutes();
  return total >= 9 * 60 && total < 15 * 60 + 30; // 09:00–15:30 KST
}

export function isAfterHours(): boolean {
  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const day = kst.getUTCDay();
  if (day === 0 || day === 6) return false;
  const total = kst.getUTCHours() * 60 + kst.getUTCMinutes();
  return total >= 15 * 60 + 30 && total < 18 * 60; // 15:30–18:00 KST
}

export function isPreMarket(): boolean {
  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const day = kst.getUTCDay();
  if (day === 0 || day === 6) return false;
  const total = kst.getUTCHours() * 60 + kst.getUTCMinutes();
  return total >= 8 * 60 && total < 9 * 60; // 08:00–09:00 KST
}

export function useRealtimePrice(stockCodes: string[]): Record<string, RealtimePrice> {
  const [prices, setPrices] = useState<Record<string, RealtimePrice>>({});
  const key = stockCodes.slice().sort().join(",");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!stockCodes.length || !isMarketOpen()) return; // 장외시간: WS 연결 생략

    const wsBase = API_BASE.replace(/^http/, "ws");
    const ws = new WebSocket(`${wsBase}/api/ws/realtime`);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ subscribe: stockCodes }));
    };

    ws.onmessage = (e) => {
      try {
        const data: RealtimePrice & { error?: string } = JSON.parse(e.data);
        if (data.error) return;
        if (data.stock_code) {
          setPrices(prev => ({ ...prev, [data.stock_code]: data }));
        }
      } catch {
        // ignore malformed frames
      }
    };

    ws.onerror = () => {};

    return () => {
      ws.close();
      wsRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return prices;
}

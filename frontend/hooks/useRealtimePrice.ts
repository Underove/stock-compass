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
  return total >= 9 * 60 && total < 15 * 60 + 30;
}

export function isAfterHours(): boolean {
  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const day = kst.getUTCDay();
  if (day === 0 || day === 6) return false;
  const total = kst.getUTCHours() * 60 + kst.getUTCMinutes();
  return total >= 15 * 60 + 30 && total < 18 * 60;
}

export function isPreMarket(): boolean {
  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const day = kst.getUTCDay();
  if (day === 0 || day === 6) return false;
  const total = kst.getUTCHours() * 60 + kst.getUTCMinutes();
  return total >= 8 * 60 && total < 9 * 60;
}

const MAX_RETRY_DELAY = 30_000;

export function useRealtimePrice(stockCodes: string[]): Record<string, RealtimePrice> {
  const [prices, setPrices] = useState<Record<string, RealtimePrice>>({});
  const key = stockCodes.slice().sort().join(",");
  const wsRef = useRef<WebSocket | null>(null);
  const retryDelay = useRef(2_000);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const destroyed = useRef(false);

  useEffect(() => {
    if (!stockCodes.length || !isMarketOpen()) return;

    destroyed.current = false;
    retryDelay.current = 2_000;

    function connect() {
      if (destroyed.current) return;

      const wsBase = API_BASE.replace(/^http/, "ws");
      const ws = new WebSocket(`${wsBase}/api/ws/realtime`);
      wsRef.current = ws;

      ws.onopen = () => {
        retryDelay.current = 2_000; // 연결 성공 시 딜레이 리셋
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
          // malformed frame 무시
        }
      };

      ws.onerror = () => {};

      // 연결 종료 시 지수 백오프로 재연결
      ws.onclose = () => {
        wsRef.current = null;
        if (destroyed.current) return;
        retryTimer.current = setTimeout(() => {
          retryDelay.current = Math.min(retryDelay.current * 2, MAX_RETRY_DELAY);
          connect();
        }, retryDelay.current);
      };
    }

    connect();

    return () => {
      destroyed.current = true;
      if (retryTimer.current) clearTimeout(retryTimer.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return prices;
}

"use client";

import { useEffect, useRef } from "react";

import type { Candle } from "../lib/types";

type Props = {
  candles: Candle[];
  height?: number;
  buyPrice?: number;
};

function calcMA(candles: Candle[], period: number): { time: string; value: number }[] {
  const result: { time: string; value: number }[] = [];
  for (let i = period - 1; i < candles.length; i++) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += candles[j].close;
    result.push({ time: candles[i].time, value: Math.round(sum / period) });
  }
  return result;
}

export function StockChart({ candles, height = 260, buyPrice }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const chartRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current || candles.length === 0) return;

    let mounted = true;

    async function init() {
      const { createChart, CandlestickSeries, HistogramSeries, LineSeries } =
        await import("lightweight-charts");
      if (!mounted || !containerRef.current) return;

      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }

      const chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height,
        layout: {
          background: { color: "transparent" },
          textColor: "#8E8E93",
          fontSize: 11,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'Pretendard Variable', sans-serif",
        },
        grid: {
          vertLines: { color: "rgba(60,60,67,0.06)" },
          horzLines: { color: "rgba(60,60,67,0.06)" },
        },
        crosshair: {
          mode: 1,
          vertLine: { color: "rgba(60,60,67,0.3)", width: 1, style: 3, labelBackgroundColor: "#3C3C43" },
          horzLine: { color: "rgba(60,60,67,0.3)", width: 1, style: 3, labelBackgroundColor: "#3C3C43" },
        },
        rightPriceScale: {
          borderVisible: false,
          scaleMargins: { top: 0.06, bottom: 0.28 },
          textColor: "#AEAEB2",
        },
        timeScale: {
          borderVisible: false,
          barSpacing: 6,
          fixLeftEdge: true,
          fixRightEdge: true,
          tickMarkFormatter: (time: number | { year: number; month: number; day: number }) => {
            if (typeof time === "object") return `${time.month}/${time.day}`;
            const d = new Date(time * 1000);
            return `${d.getMonth() + 1}/${d.getDate()}`;
          },
        },
        handleScroll: { mouseWheel: true, pressedMouseMove: true },
        handleScale: { mouseWheel: true, pinch: true },
      });

      chartRef.current = chart;

      // ── 캔들스틱 ──
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: "#FF3B30",
        downColor: "#007AFF",
        borderUpColor: "#FF3B30",
        borderDownColor: "#007AFF",
        wickUpColor: "#FF3B30",
        wickDownColor: "#007AFF",
        borderVisible: true,
      });

      const validCandles = candles.filter(
        c => isFinite(c.open) && isFinite(c.high) && isFinite(c.low) && isFinite(c.close)
      );
      const candleData = validCandles.map((c) => ({
        time: c.time as `${number}-${number}-${number}`,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));
      candleSeries.setData(candleData);

      // ── 매수단가 기준선 ──
      if (buyPrice && buyPrice > 0) {
        candleSeries.createPriceLine({
          price: buyPrice,
          color: "rgba(255,149,0,0.9)",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "매수",
        });
      }

      // ── MA5 ──
      const ma5Data = calcMA(validCandles, 5);
      if (ma5Data.length > 0) {
        const ma5 = chart.addSeries(LineSeries, {
          color: "rgba(255,214,10,0.85)",
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        ma5.setData(ma5Data.map(d => ({ time: d.time as `${number}-${number}-${number}`, value: d.value })));
      }

      // ── MA20 ──
      const ma20Data = calcMA(validCandles, 20);
      if (ma20Data.length > 0) {
        const ma20 = chart.addSeries(LineSeries, {
          color: "rgba(191,90,242,0.75)",
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        ma20.setData(ma20Data.map(d => ({ time: d.time as `${number}-${number}-${number}`, value: d.value })));
      }

      // ── 거래량 히스토그램 ──
      const volumeSeries = chart.addSeries(HistogramSeries, {
        priceScaleId: "volume",
        priceLineVisible: false,
        lastValueVisible: false,
      });
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.78, bottom: 0 },
        borderVisible: false,
        textColor: "transparent",
      });

      volumeSeries.setData(
        validCandles.map((c) => ({
          time: c.time as `${number}-${number}-${number}`,
          value: isFinite(c.volume) ? c.volume : 0,
          color: c.close >= c.open ? "rgba(255,59,48,0.35)" : "rgba(0,122,255,0.35)",
        })),
      );

      chart.timeScale().fitContent();
    }

    init();

    const el = containerRef.current;
    const observer = new ResizeObserver(() => {
      if (chartRef.current && el) {
        chartRef.current.applyOptions({ width: el.clientWidth });
      }
    });
    observer.observe(el);

    return () => {
      mounted = false;
      observer.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [candles, height, buyPrice]);

  return (
    <div style={{ position: "relative", width: "100%" }}>
      <div ref={containerRef} style={{ width: "100%", height, borderRadius: 8, overflow: "hidden" }} />
      {/* MA 범례 */}
      <div style={{
        position: "absolute", top: 6, left: 8,
        display: "flex", gap: 10, pointerEvents: "none",
      }}>
        <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "rgba(255,214,10,0.9)", fontWeight: 700 }}>
          <span style={{ width: 16, height: 1.5, background: "rgba(255,214,10,0.85)", display: "inline-block", borderRadius: 1 }} />
          MA5
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "rgba(191,90,242,0.9)", fontWeight: 700 }}>
          <span style={{ width: 16, height: 1.5, background: "rgba(191,90,242,0.75)", display: "inline-block", borderRadius: 1 }} />
          MA20
        </span>
        {buyPrice && (
          <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "rgba(255,149,0,0.9)", fontWeight: 700 }}>
            <span style={{ width: 16, height: 1.5, background: "rgba(255,149,0,0.85)", display: "inline-block", borderRadius: 1, borderTop: "1.5px dashed rgba(255,149,0,0.85)" }} />
            매수
          </span>
        )}
      </div>
    </div>
  );
}

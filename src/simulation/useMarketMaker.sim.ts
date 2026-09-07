/** @SIMULATION_ONLY - Browser paper-trading, Supabase-backed, DOES NOT PLACE REAL ORDERS. Real orders only via bot/ worker. */
export const IS_RESEARCH_SIMULATION_ONLY = true;
export const RESEARCH_SIMULATION_NAME = "Research Simulation — Binance/Generic";
/** This legacy research simulator is never used for Polymarket market making. */
export const MARKET_DATA_SOURCE = "DEMO" as const;
export const AUXILIARY_DATA_SOURCE = "REAL_BINANCE" as const;

import { useCallback, useEffect, useRef, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { getCooldown, logTrade } from "@/lib/trading.functions";

export interface ResearchSimulationFill {
  ts: number;
  side: "BUY" | "SELL";
  price: number;
  size: number;
  pnl: number;
}

export interface ResearchSimulationOptions {
  symbol: string; // e.g. btcusdt
  market: string; // logical market label persisted with trades
  spreadBps: number;
  sizeUsd: number;
  running: boolean;
  cooldownSeconds: number;
}

const MIN_FILL_GAP_MS = 4000;

/**
 * Legacy research-only Binance/generic simulation. It is not a Polymarket
 * market-data or execution path.
 */
export function useResearchSimulation(opts: ResearchSimulationOptions) {
  const { symbol, market, spreadBps, sizeUsd, running, cooldownSeconds } = opts;
  const log = useServerFn(logTrade);
  const cooldown = useServerFn(getCooldown);

  const [price, setPrice] = useState<number | null>(null);
  const [connected, setConnected] = useState(false);
  const [fills, setFills] = useState<ResearchSimulationFill[]>([]);
  const [inventory, setInventory] = useState(0);
  const [realizedPnl, setRealizedPnl] = useState(0);

  const lastFillRef = useRef(0);
  const avgCostRef = useRef(0);
  const invRef = useRef(0);
  const runningRef = useRef(running);
  runningRef.current = running;

  const half = spreadBps / 10_000 / 2;
  const bid = price !== null ? price * (1 - half) : null;
  const ask = price !== null ? price * (1 + half) : null;

  const onFill = useCallback(
    async (side: "BUY" | "SELL", fillPrice: number) => {
      const qty = sizeUsd / fillPrice;
      let pnl = 0;
      if (side === "BUY") {
        const newInv = invRef.current + qty;
        avgCostRef.current =
          newInv > 0 ? (avgCostRef.current * invRef.current + fillPrice * qty) / newInv : fillPrice;
        invRef.current = newInv;
      } else {
        pnl =
          (fillPrice - (avgCostRef.current || fillPrice)) *
          Math.min(qty, Math.max(invRef.current, 0));
        invRef.current -= qty;
      }
      setInventory(Math.round(invRef.current * 1e6) / 1e6);
      setRealizedPnl((p) => Math.round((p + pnl) * 100) / 100);
      setFills((f) =>
        [{ ts: Date.now(), side, price: fillPrice, size: qty, pnl }, ...f].slice(0, 50),
      );

      try {
        await log({
          data: {
            table: "mm_trades",
            market,
            side,
            price: fillPrice,
            size: qty,
            pnl,
            strategy: "market_making",
          },
        });
        await cooldown({ data: { market, arm: true, cooldownSeconds } });
      } catch {
        /* fill stays local if persistence fails */
      }
    },
    [cooldown, cooldownSeconds, log, market, sizeUsd],
  );

  useEffect(() => {
    const ws = new WebSocket(`wss://stream.binance.com:9443/ws/${symbol}@trade`);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as { p?: string };
        const p = Number(msg.p);
        if (!Number.isFinite(p)) return;
        setPrice((prev) => {
          if (
            runningRef.current &&
            prev !== null &&
            Date.now() - lastFillRef.current > MIN_FILL_GAP_MS
          ) {
            const h = spreadBps / 10_000 / 2;
            if (p <= prev * (1 - h)) {
              lastFillRef.current = Date.now();
              void onFill("BUY", p);
            } else if (p >= prev * (1 + h) && invRef.current > 0) {
              lastFillRef.current = Date.now();
              void onFill("SELL", p);
            }
          }
          return p;
        });
      } catch {
        /* ignore malformed frame */
      }
    };
    return () => ws.close();
  }, [symbol, spreadBps, onFill]);

  const unrealized =
    price !== null && inventory !== 0 ? (price - avgCostRef.current) * inventory : 0;

  return {
    price,
    bid,
    ask,
    connected,
    fills,
    inventory,
    realizedPnl,
    unrealizedPnl: Math.round(unrealized * 100) / 100,
    avgCost: avgCostRef.current,
  };
}

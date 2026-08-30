import { useCallback, useEffect, useRef, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { getCooldown, logTrade } from "@/lib/trading.functions";

export interface MmFill {
  ts: number;
  side: "BUY" | "SELL";
  price: number;
  size: number;
  pnl: number;
}

export interface MmOptions {
  symbol: string; // e.g. btcusdt
  market: string; // logical market label persisted with trades
  spreadBps: number;
  sizeUsd: number;
  running: boolean;
  cooldownSeconds: number;
}

const MIN_FILL_GAP_MS = 4000;

/**
 * Client-side market-making loop: live WebSocket price feed, two-sided quotes
 * around mid, simulated fills when the tape crosses a quote. Every fill is
 * persisted through the log_trade server function and arms the cooldown.
 */
export function useMarketMaker(opts: MmOptions) {
  const { symbol, market, spreadBps, sizeUsd, running, cooldownSeconds } = opts;
  const log = useServerFn(logTrade);
  const cooldown = useServerFn(getCooldown);

  const [price, setPrice] = useState<number | null>(null);
  const [connected, setConnected] = useState(false);
  const [fills, setFills] = useState<MmFill[]>([]);
  const [inventory, setInventory] = useState(0);
  const [realizedPnl, setRealizedPnl] = useState(0);

  const lastFillRef = useRef(0);
  const avgCostRef = useRef(0);
  const invRef = useRef(0);
  const runningRef = useRef(running);
  runningRef.current = running;

  const half = (spreadBps / 10_000) / 2;
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
        pnl = (fillPrice - (avgCostRef.current || fillPrice)) * Math.min(qty, Math.max(invRef.current, 0));
        invRef.current -= qty;
      }
      setInventory(Math.round(invRef.current * 1e6) / 1e6);
      setRealizedPnl((p) => Math.round((p + pnl) * 100) / 100);
      setFills((f) => [{ ts: Date.now(), side, price: fillPrice, size: qty, pnl }, ...f].slice(0, 50));

      try {
        await log({
          data: { table: "mm_trades", market, side, price: fillPrice, size: qty, pnl, strategy: "market_making" },
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
          if (runningRef.current && prev !== null && Date.now() - lastFillRef.current > MIN_FILL_GAP_MS) {
            const h = (spreadBps / 10_000) / 2;
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

  const unrealized = price !== null && inventory !== 0 ? (price - avgCostRef.current) * inventory : 0;

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

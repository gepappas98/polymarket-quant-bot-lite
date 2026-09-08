import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { getCooldown, logTrade } from "@/lib/trading.functions";

const CLOB_MARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market";
const STALE_AFTER_MS = 45_000;
const MIN_FILL_GAP_MS = 4_000;

export type L2Level = { price: number; shares: number };
export type MmFill = {
  ts: number;
  side: "BUY" | "SELL";
  price: number;
  size: number;
  pnl: number;
  label: "SIMULATED";
};
export type MmBook = { bids: L2Level[]; asks: L2Level[]; timestamp: number };

export type MmOptions = {
  tokenId: string;
  marketId: string;
  spreadBps: number;
  sizeUsd: number;
  running: boolean;
  cooldownSeconds: number;
};

function numberValue(value: unknown): number | null {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function normalizeL2Levels(levels: unknown, descending: boolean): L2Level[] {
  if (!Array.isArray(levels)) return [];
  return levels
    .map((level) => {
      const row = level as Record<string, unknown>;
      return { price: numberValue(row["price"]), shares: numberValue(row["size"] ?? row["shares"]) };
    })
    .filter(
      (level): level is { price: number; shares: number } =>
        level.price !== null && level.shares !== null && level.price > 0 && level.shares > 0,
    )
    .sort((a, b) => (descending ? b.price - a.price : a.price - b.price));
}

export function applyClobMessage(book: MmBook | null, message: unknown, tokenId: string): MmBook | null {
  if (!message || typeof message !== "object") return book;
  const event = message as Record<string, unknown>;
  const eventType = event["event_type"] ?? event["type"];
  const assetId = String(event["asset_id"] ?? event["assetId"] ?? "");
  const now = Date.now();

  if (eventType === "book" && assetId === tokenId) {
    return {
      bids: normalizeL2Levels(event["bids"], true),
      asks: normalizeL2Levels(event["asks"], false),
      timestamp: now,
    };
  }

  if (eventType !== "price_change" || !book) return book;
  let changed = false;
  const next = { bids: [...book.bids], asks: [...book.asks], timestamp: book.timestamp };
  for (const rawChange of Array.isArray(event["price_changes"]) ? event["price_changes"] : []) {
    if (!rawChange || typeof rawChange !== "object") continue;
    const change = rawChange as Record<string, unknown>;
    if (String(change["asset_id"] ?? change["assetId"] ?? "") !== tokenId) continue;
    const price = numberValue(change["price"]);
    const shares = numberValue(change["size"]);
    const side = String(change["side"] ?? "").toUpperCase();
    if (price === null || shares === null || !["BUY", "SELL"].includes(side)) continue;
    const key = side === "BUY" ? "bids" : "asks";
    next[key] = next[key].filter((level) => level.price !== price);
    if (shares > 0) next[key].push({ price, shares });
    next[key].sort((a, b) => (key === "bids" ? b.price - a.price : a.price - b.price));
    changed = true;
  }
  return changed ? { ...next, timestamp: now } : book;
}

export function getBookMetrics(book: MmBook | null, now = Date.now()) {
  const bestBid = book?.bids[0]?.price ?? null;
  const bestAsk = book?.asks[0]?.price ?? null;
  const mid = bestBid !== null && bestAsk !== null ? (bestBid + bestAsk) / 2 : null;
  return {
    bestBid,
    bestAsk,
    mid,
    spread: bestBid !== null && bestAsk !== null ? bestAsk - bestBid : null,
    bidDepth: book?.bids.reduce((sum, level) => sum + level.shares, 0) ?? 0,
    askDepth: book?.asks.reduce((sum, level) => sum + level.shares, 0) ?? 0,
    timestamp: book?.timestamp ?? null,
    stale: !book || now - book.timestamp > STALE_AFTER_MS,
  };
}

export function usePolymarketMarketMaker(options: MmOptions) {
  const { tokenId, marketId, spreadBps, sizeUsd, running, cooldownSeconds } = options;
  const log = useServerFn(logTrade);
  const cooldown = useServerFn(getCooldown);
  const [book, setBook] = useState<MmBook | null>(null);
  const [connected, setConnected] = useState(false);
  const [fills, setFills] = useState<MmFill[]>([]);
  const [inventory, setInventory] = useState(0);
  const [realizedPnl, setRealizedPnl] = useState(0);
  const [now, setNow] = useState(Date.now());
  const inventoryRef = useRef(0);
  const avgCostRef = useRef(0);
  const lastFillRef = useRef(0);
  const previousMetricsRef = useRef<ReturnType<typeof getBookMetrics> | null>(null);
  const runningRef = useRef(running);
  runningRef.current = running;

  const metrics = useMemo(() => getBookMetrics(book, now), [book, now]);
  const quoteHalfSpread = spreadBps / 20_000;
  const bid = !metrics.stale && metrics.mid !== null ? metrics.mid * (1 - quoteHalfSpread) : null;
  const ask = !metrics.stale && metrics.mid !== null ? metrics.mid * (1 + quoteHalfSpread) : null;

  const recordFill = useCallback(
    async (side: "BUY" | "SELL", price: number, availableShares: number) => {
      const requestedShares = sizeUsd / price;
      const size = Math.min(requestedShares, availableShares);
      if (!Number.isFinite(size) || size <= 0) return;
      let pnl = 0;
      if (side === "BUY") {
        const nextInventory = inventoryRef.current + size;
        avgCostRef.current = (avgCostRef.current * inventoryRef.current + price * size) / nextInventory;
        inventoryRef.current = nextInventory;
      } else {
        const closingShares = Math.min(size, Math.max(inventoryRef.current, 0));
        if (closingShares <= 0) return;
        pnl = (price - avgCostRef.current) * closingShares;
        inventoryRef.current -= closingShares;
      }
      setInventory(Math.round(inventoryRef.current * 1e6) / 1e6);
      setRealizedPnl((current) => Math.round((current + pnl) * 100) / 100);
      setFills((current) => [{ ts: Date.now(), side, price, size, pnl, label: "SIMULATED" as const }, ...current].slice(0, 50));
      try {
        await log({
          data: { table: "mm_trades", market: marketId, side, price, size, pnl, strategy: "PAPER_SIMULATED_MM" },
        });
        await cooldown({ data: { market: marketId, arm: true, cooldownSeconds } });
      } catch {
        // The local paper receipt remains visible if persistence is unavailable.
      }
    },
    [cooldown, cooldownSeconds, log, marketId, sizeUsd],
  );

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!tokenId.trim()) {
      setBook(null);
      setConnected(false);
      previousMetricsRef.current = null;
      return;
    }
    let closed = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let socket: WebSocket | undefined;
    let retryMs = 1_000;

    const connect = () => {
      socket = new WebSocket(CLOB_MARKET_WS_URL);
      socket.onopen = () => {
        if (closed || !socket) return;
        retryMs = 1_000;
        setConnected(true);
        socket.send(JSON.stringify({ assets_ids: [tokenId], type: "market", initial_dump: true, custom_feature_enabled: true }));
      };
      socket.onmessage = (event) => {
        try {
          const nextBook = applyClobMessage(bookRef.current, JSON.parse(String(event.data)), tokenId);
          if (nextBook !== bookRef.current) {
            bookRef.current = nextBook;
            setBook(nextBook);
            setNow(Date.now());
          }
        } catch {
          // Ignore malformed public market-channel frames.
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!closed) {
          retryTimer = setTimeout(connect, retryMs);
          retryMs = Math.min(retryMs * 2, 30_000);
        }
      };
      socket.onerror = () => socket?.close();
    };
    const bookRef = { current: null as MmBook | null };
    connect();
    return () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      socket?.close();
    };
  }, [tokenId]);

  useEffect(() => {
    const previous = previousMetricsRef.current;
    previousMetricsRef.current = metrics;
    if (!runningRef.current || metrics.stale || !previous || Date.now() - lastFillRef.current <= MIN_FILL_GAP_MS) return;
    if (bid !== null && metrics.bestAsk !== null && metrics.bestAsk <= bid) {
      lastFillRef.current = Date.now();
      void recordFill("BUY", metrics.bestAsk, book?.asks[0]?.shares ?? 0);
    } else if (ask !== null && metrics.bestBid !== null && metrics.bestBid >= ask && inventoryRef.current > 0) {
      lastFillRef.current = Date.now();
      void recordFill("SELL", metrics.bestBid, Math.min(book?.bids[0]?.shares ?? 0, inventoryRef.current));
    }
  }, [ask, bid, book, metrics, recordFill]);

  const unrealizedPnl = metrics.mid !== null && !metrics.stale ? (metrics.mid - avgCostRef.current) * inventory : 0;
  return { ...metrics, bid, ask, connected, fills, inventory, realizedPnl, unrealizedPnl: Math.round(unrealizedPnl * 100) / 100, avgCost: avgCostRef.current };
}

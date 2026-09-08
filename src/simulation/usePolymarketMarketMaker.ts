/** Real Polymarket CLOB L2 market data with PAPER execution only. */
import { useCallback, useEffect, useRef, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { getCooldown, logTrade } from "@/lib/trading.functions";
import type { PolymarketBookLevel } from "@/lib/polymarket.types";

export const MARKET_DATA_SOURCE = "REAL_POLYMARKET_CLOB_WS" as const;
export const EXECUTION_MODE = "PAPER" as const;
export const FILL_STATUS = "SIMULATED" as const;
export const STALE_AFTER_MS = 45_000;
const WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market";

export type RealMmBook = {
  bids: PolymarketBookLevel[];
  asks: PolymarketBookLevel[];
  timestamp: string | null;
  hash?: string | undefined;
};

export type RealMmState = {
  marketId: string;
  tokenId: string;
  connected: boolean;
  stale: boolean;
  lastError: string | null;
  book: RealMmBook | null;
  bestBid: number | null;
  bestAsk: number | null;
  mid: number | null;
  spread: number | null;
  bidDepth: number;
  askDepth: number;
};

export type MmFill = {
  ts: number;
  side: "BUY" | "SELL";
  price: number;
  size: number;
  pnl: number;
  executionMode: typeof EXECUTION_MODE;
  status: typeof FILL_STATUS;
};

function level(raw: unknown): PolymarketBookLevel | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;
  const price = Number(item["price"]);
  const shares = Number(item["size"] ?? item["shares"]);
  return Number.isFinite(price) && price > 0 && Number.isFinite(shares) && shares > 0 ? { price, shares } : null;
}

function levels(raw: unknown, descending: boolean): PolymarketBookLevel[] {
  return (Array.isArray(raw) ? raw : []).map(level).filter((x): x is PolymarketBookLevel => x !== null).sort((a, b) => descending ? b.price - a.price : a.price - b.price);
}

export function applyPolymarketMarketMessage(current: RealMmBook | null, raw: unknown, tokenId: string): RealMmBook | null {
  const messages = Array.isArray(raw) ? raw : [raw];
  let next = current;
  for (const item of messages) {
    if (!item || typeof item !== "object") continue;
    const message = item as Record<string, unknown>;
    const eventType = String(message["event_type"] ?? message["type"] ?? "");
    const asset = String(message["asset_id"] ?? message["assetId"] ?? "");
    if (asset && asset !== tokenId) continue;
    if (eventType === "book") {
      const hash = typeof message["hash"] === "string" ? message["hash"] : undefined;
      next = hash === undefined
        ? { bids: levels(message["bids"], true), asks: levels(message["asks"], false), timestamp: message["timestamp"] == null ? null : String(message["timestamp"]) }
        : { bids: levels(message["bids"], true), asks: levels(message["asks"], false), timestamp: message["timestamp"] == null ? null : String(message["timestamp"]), hash };
    } else if (eventType === "price_change") {
      const base = next ?? { bids: [], asks: [], timestamp: null };
      let bids = [...base.bids];
      let asks = [...base.asks];
      const changes = Array.isArray(message["price_changes"]) ? message["price_changes"] : Array.isArray(message["priceChanges"]) ? message["priceChanges"] : [];
      for (const rawChange of changes) {
        if (!rawChange || typeof rawChange !== "object") continue;
        const change = rawChange as Record<string, unknown>;
        const changeAsset = String(change["asset_id"] ?? change["assetId"] ?? change["tokenId"] ?? tokenId);
        if (changeAsset !== tokenId) continue;
        const price = Number(change["price"]);
        const size = Number(change["size"]);
        if (!Number.isFinite(price) || price <= 0 || !Number.isFinite(size) || size < 0) continue;
        const changeSide = String(change["side"] ?? "").toUpperCase();
        const target = changeSide === "BUY" ? bids : changeSide === "SELL" ? asks : null;
        if (!target) continue;
        const remaining = target.filter((x) => x.price !== price);
        if (size > 0) remaining.push({ price, shares: size });
        remaining.sort((a, b) => target === bids ? b.price - a.price : a.price - b.price);
        if (target === bids) bids = remaining; else asks = remaining;
      }
      const timestamp = message["timestamp"] == null ? base.timestamp : String(message["timestamp"]);
      const hash = typeof message["hash"] === "string" ? message["hash"] : base.hash;
      next = hash === undefined ? { ...base, bids, asks, timestamp } : { ...base, bids, asks, timestamp, hash };
    }
  }
  return next;
}

export function bookMetrics(book: RealMmBook | null) {
  const bestBid = book?.bids[0]?.price ?? null;
  const bestAsk = book?.asks[0]?.price ?? null;
  return {
    bestBid,
    bestAsk,
    mid: bestBid !== null && bestAsk !== null ? (bestBid + bestAsk) / 2 : null,
    spread: bestBid !== null && bestAsk !== null ? bestAsk - bestBid : null,
    bidDepth: (book?.bids ?? []).reduce((sum, x) => sum + x.shares, 0),
    askDepth: (book?.asks ?? []).reduce((sum, x) => sum + x.shares, 0),
  };
}

export function simulatePaperDepthFill(book: RealMmBook, side: "BUY" | "SELL", sizeUsd: number) {
  const levelsToConsume = side === "BUY" ? book.asks : book.bids;
  let remainingUsd = Math.max(0, sizeUsd);
  let shares = 0;
  let notional = 0;
  for (const level of levelsToConsume) {
    if (remainingUsd <= 0) break;
    const clipUsd = Math.min(remainingUsd, level.price * level.shares);
    shares += clipUsd / level.price;
    notional += clipUsd;
    remainingUsd -= clipUsd;
  }
  if (!shares) return null;
  return { shares, sizeUsd: notional, price: notional / shares, partial: remainingUsd > 1e-9 };
}

export interface MmOptions { marketId: string; tokenId: string; spreadBps: number; sizeUsd: number; running: boolean; cooldownSeconds: number }

export function usePolymarketMarketMaker(opts: MmOptions) {
  const { marketId, tokenId, spreadBps, sizeUsd, running, cooldownSeconds } = opts;
  const log = useServerFn(logTrade);
  const cooldown = useServerFn(getCooldown);
  const [state, setState] = useState<RealMmState>({ marketId, tokenId, connected: false, stale: true, lastError: null, book: null, ...bookMetrics(null) });
  const [fills, setFills] = useState<MmFill[]>([]);
  const [inventory, setInventory] = useState(0);
  const [realizedPnl, setRealizedPnl] = useState(0);
  const avgCostRef = useRef(0);
  const lastFillRef = useRef(0);
  const runningRef = useRef(running);
  runningRef.current = running;

  const onBook = useCallback((raw: unknown) => {
    setState((previous) => {
      const book = applyPolymarketMarketMessage(previous.book, raw, tokenId);
      return { ...previous, book, stale: true, ...bookMetrics(book) };
    });
  }, [tokenId]);

  useEffect(() => {
    if (!tokenId.trim()) {
      setState((previous) => ({ ...previous, connected: false, stale: true, lastError: "token_id is required" }));
      return;
    }
    const ws = new WebSocket(WS_URL);
    const heartbeat = window.setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send("PING"); }, 10_000);
    const staleTimer = window.setInterval(() => setState((previous) => ({ ...previous, stale: !previous.book || !previous.book.timestamp || Date.now() - Number(previous.book.timestamp) > STALE_AFTER_MS })), 1_000);
    ws.onopen = () => { setState((previous) => ({ ...previous, connected: true, lastError: null })); ws.send(JSON.stringify({ assets_ids: [tokenId], type: "market", initial_dump: true, custom_feature_enabled: true })); };
    ws.onclose = () => setState((previous) => ({ ...previous, connected: false, stale: true }));
    ws.onerror = () => setState((previous) => ({ ...previous, connected: false, stale: true, lastError: "Polymarket CLOB WebSocket unavailable" }));
    ws.onmessage = (event) => { try { onBook(JSON.parse(String(event.data))); } catch { setState((previous) => ({ ...previous, lastError: "Malformed Polymarket CLOB event" })); } };
    return () => { window.clearInterval(heartbeat); window.clearInterval(staleTimer); ws.close(); };
  }, [onBook, tokenId]);

  useEffect(() => {
    if (!runningRef.current || state.stale || state.mid === null || state.bestBid === null || state.bestAsk === null) return;
    const quoteBid = state.mid * (1 - spreadBps / 20_000);
    const quoteAsk = state.mid * (1 + spreadBps / 20_000);
    const canBuy = state.bestAsk <= quoteBid && Date.now() - lastFillRef.current > 4000;
    const canSell = state.bestBid >= quoteAsk && inventory > 0 && Date.now() - lastFillRef.current > 4000;
    if (!canBuy && !canSell) return;
    const side: "BUY" | "SELL" = canBuy ? "BUY" : "SELL";
    const fill = state.book ? simulatePaperDepthFill(state.book, side, sizeUsd) : null;
    if (!fill) return;
    const price = fill.price;
    const qty = fill.shares;
    lastFillRef.current = Date.now();
    const pnl = side === "SELL" ? (price - avgCostRef.current) * Math.min(qty, inventory) : 0;
    if (side === "BUY") { const total = inventory + qty; avgCostRef.current = total ? (avgCostRef.current * inventory + price * qty) / total : price; setInventory(total); } else setInventory((value) => value - qty);
    setRealizedPnl((value) => value + pnl);
    setFills((previous) => [{ ts: Date.now(), side, price, size: qty, pnl, executionMode: EXECUTION_MODE, status: FILL_STATUS }, ...previous].slice(0, 50));
    void log({ data: { table: "mm_trades", market: `${marketId}:${tokenId}`, side, price, size: qty, pnl, strategy: "market_making_paper_simulated" } }).catch(() => undefined);
    void cooldown({ data: { market: `${marketId}:${tokenId}`, arm: true, cooldownSeconds } }).catch(() => undefined);
  }, [cooldown, cooldownSeconds, inventory, log, marketId, sizeUsd, spreadBps, state]);

  return { ...state, price: state.mid, bid: state.bestBid, ask: state.bestAsk, fills, inventory, realizedPnl, unrealizedPnl: state.mid !== null ? (state.mid - avgCostRef.current) * inventory : 0, avgCost: avgCostRef.current, executionMode: EXECUTION_MODE, fillStatus: FILL_STATUS, marketDataSource: MARKET_DATA_SOURCE };
}

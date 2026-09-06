/**
 * Sprint 2 — paper adapter implementing the same ExchangeAdapter surface as a
 * real venue. It fills against a simple quote/depth map so the executor path is
 * identical in paper and live.
 */

import type { ExchangeAdapter, PlaceOrderRequest, PlaceOrderResult, VenueOrderSnapshot } from "./adapter";
import type { BookLevel, Fill } from "./models";
import { round6 } from "./models";
import type { Clock } from "./clock";
import { systemClock } from "./clock";

export interface PaperQuote {
  /** Full L2 asks, sorted best-to-worst by the adapter. */
  asks?: BookLevel[];
  /** Full L2 bids, sorted best-to-worst by the adapter. */
  bids?: BookLevel[];
  /** Legacy top-of-book fields are normalized into one-level depth. */
  ask?: number;
  askShares?: number;
  bid?: number;
  bidShares?: number;
  feeBps?: number;
}

type StoredOrder = {
  req: PlaceOrderRequest;
  venueOrderId: string;
  fills: Fill[];
  open: boolean;
  cancelled: boolean;
  rejected: boolean;
};

export class PaperAdapter implements ExchangeAdapter {
  readonly name = "paper";
  private orders = new Map<string, StoredOrder>();
  private seq = 0;

  constructor(
    private quotes: Record<string, PaperQuote>,
    private clock: Clock = systemClock,
  ) {}

  setQuotes(quotes: Record<string, PaperQuote>): void {
    this.quotes = quotes;
  }

  async placeOrder(req: PlaceOrderRequest): Promise<PlaceOrderResult> {
    const existing = this.orders.get(req.clientOrderId);
    if (existing) {
      // Idempotent re-submit: return the venue's current truth, never a new order.
      return {
        accepted: !existing.rejected,
        venueOrderId: existing.venueOrderId,
        fills: existing.fills,
        closed: !existing.open,
      };
    }

    const quote = this.quotes[req.market];
    if (!quote) {
      this.orders.set(req.clientOrderId, {
        req,
        venueOrderId: `paper-${++this.seq}`,
        fills: [],
        open: false,
        cancelled: false,
        rejected: true,
      });
      return { accepted: false, venueOrderId: null, fills: [], closed: true, rejectReason: "no quote for market" };
    }

    const action = req.action ?? "BUY";
    const rawLevels = action === "BUY"
      ? (quote.asks ?? (quote.ask ? [{ price: quote.ask, shares: quote.askShares ?? req.sizeShares }] : []))
      : (quote.bids ?? (quote.bid ? [{ price: quote.bid, shares: quote.bidShares ?? req.sizeShares }] : []));
    const levels = [...rawLevels]
      .filter((level) => level.price > 0 && level.shares > 0)
      .sort((a, b) => action === "BUY" ? a.price - b.price : b.price - a.price);
    const feeBps = quote.feeBps ?? 0;
    const fills: Fill[] = [];
    let remaining = req.sizeShares;
    for (const level of levels) {
      if (remaining <= 1e-9) break;
      const tradable = req.orderType === "MARKET" || (action === "BUY" ? req.price >= level.price : req.price <= level.price);
      if (!tradable) break;
      const shares = round6(Math.min(remaining, level.shares));
      fills.push({
        fillId: `${req.clientOrderId}:${fills.length + 1}`,
        price: level.price,
        shares,
        fee: round6((shares * level.price * feeBps) / 10_000),
        filledAt: this.clock.isoNow(),
      });
      remaining = round6(remaining - shares);
    }
    const shares = fills.reduce((sum, fill) => sum + fill.shares, 0);
    let consumed = 0;
    for (const level of levels) {
      const fillShares = fills
        .filter((fill) => fill.price === level.price)
        .reduce((sum, fill) => sum + fill.shares, 0);
      if (fillShares <= 0) continue;
      level.shares = round6(Math.max(0, level.shares - Math.min(level.shares, fillShares)));
      consumed += fillShares;
      if (consumed >= shares - 1e-9) break;
    }

    const open = shares < req.sizeShares && req.orderType === "LIMIT";
    this.orders.set(req.clientOrderId, {
      req,
      venueOrderId: `paper-${++this.seq}`,
      fills,
      open,
      cancelled: false,
      rejected: false,
    });
    const stored = this.orders.get(req.clientOrderId)!;
    return { accepted: true, venueOrderId: stored.venueOrderId, fills, closed: !open };
  }

  /** Simulate the rest of a resting limit order filling later. */
  fillRemaining(clientOrderId: string, shares: number, price: number, fee = 0): Fill | null {
    const stored = this.orders.get(clientOrderId);
    if (!stored || !stored.open) return null;
    const filled = stored.fills.reduce((s, f) => s + f.shares, 0);
    const shareCount = round6(Math.min(shares, stored.req.sizeShares - filled));
    if (shareCount <= 0) return null;
    const fill: Fill = {
      fillId: `${clientOrderId}:${stored.fills.length + 1}`,
      price,
      shares: shareCount,
      fee,
      filledAt: this.clock.isoNow(),
    };
    stored.fills.push(fill);
    if (filled + shareCount >= stored.req.sizeShares - 1e-6) stored.open = false;
    return fill;
  }

  async cancelOrder(ref: { clientOrderId: string; venueOrderId?: string | null }): Promise<{ cancelled: boolean }> {
    const stored = this.orders.get(ref.clientOrderId);
    if (!stored) return { cancelled: false };
    if (!stored.open) return { cancelled: false };
    stored.open = false;
    stored.cancelled = true;
    return { cancelled: true };
  }

  async fetchOrders(clientOrderIds: string[]): Promise<VenueOrderSnapshot[]> {
    return clientOrderIds
      .map((id) => this.orders.get(id))
      .filter((o): o is StoredOrder => Boolean(o))
      .map((o) => ({
        clientOrderId: o.req.clientOrderId,
        venueOrderId: o.venueOrderId,
        fills: o.fills,
        open: o.open,
        cancelled: o.cancelled,
        rejected: o.rejected,
      }));
  }
}

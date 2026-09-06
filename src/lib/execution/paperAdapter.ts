/**
 * Sprint 2 — paper adapter implementing the same ExchangeAdapter surface as a
 * real venue. It fills against a simple quote/depth map so the executor path is
 * identical in paper and live.
 */

import type { ExchangeAdapter, PlaceOrderRequest, PlaceOrderResult, VenueOrderSnapshot } from "./adapter";
import type { Fill } from "./models";
import { round6 } from "./models";
import type { Clock } from "./clock";
import { systemClock } from "./clock";

export interface PaperQuote {
  /** Best ask (buy price) and its available shares. */
  ask: number;
  askShares?: number;
  bid?: number;
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

    const price = req.orderType === "MARKET" ? quote.ask : Math.min(req.price, quote.ask);
    const tradable = req.orderType === "MARKET" || req.price >= quote.ask;
    const available = quote.askShares ?? req.sizeShares;
    const shares = tradable ? round6(Math.min(req.sizeShares, available)) : 0;
    const feeBps = quote.feeBps ?? 0;

    const fills: Fill[] =
      shares > 0
        ? [
            {
              fillId: `${req.clientOrderId}:1`,
              price,
              shares,
              fee: round6((shares * price * feeBps) / 10_000),
              filledAt: this.clock.isoNow(),
            },
          ]
        : [];

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

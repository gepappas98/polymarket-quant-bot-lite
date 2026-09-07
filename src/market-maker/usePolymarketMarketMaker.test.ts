import { describe, expect, it } from "vitest";
import { applyClobMessage, getBookMetrics } from "./usePolymarketMarketMaker";

describe("Polymarket market-maker CLOB book", () => {
  it("uses real snapshot depth and derives L2 metrics", () => {
    const book = applyClobMessage(null, {
      event_type: "book",
      asset_id: "token-1",
      bids: [{ price: "0.48", size: "12" }, { price: "0.49", size: "5" }],
      asks: [{ price: "0.52", size: "7" }, { price: "0.51", size: "3" }],
    }, "token-1");

    const metrics = getBookMetrics(book, book!.timestamp);
    expect(metrics).toMatchObject({
      bestBid: 0.49,
      bestAsk: 0.51,
      mid: 0.5,
      bidDepth: 17,
      askDepth: 10,
      stale: false,
    });
    expect(metrics.spread).toBeCloseTo(0.02);
  });

  it("applies only matching-token incremental CLOB updates", () => {
    const snapshot = applyClobMessage(null, {
      event_type: "book",
      asset_id: "token-1",
      bids: [{ price: "0.49", size: "5" }],
      asks: [{ price: "0.51", size: "3" }],
    }, "token-1");
    const updated = applyClobMessage(snapshot, {
      event_type: "price_change",
      price_changes: [
        { asset_id: "other-token", side: "BUY", price: "0.99", size: "99" },
        { asset_id: "token-1", side: "BUY", price: "0.50", size: "4" },
        { asset_id: "token-1", side: "SELL", price: "0.51", size: "0" },
      ],
    }, "token-1");

    expect(updated?.bids).toEqual([{ price: 0.5, shares: 4 }, { price: 0.49, shares: 5 }]);
    expect(updated?.asks).toEqual([]);
  });

  it("fails closed as stale when there is no current real book", () => {
    expect(getBookMetrics(null)).toMatchObject({ stale: true, bestBid: null, bestAsk: null, mid: null });
    const oldBook = { bids: [{ price: 0.49, shares: 5 }], asks: [{ price: 0.51, shares: 5 }], timestamp: 1 };
    expect(getBookMetrics(oldBook, 50_000).stale).toBe(true);
  });
});

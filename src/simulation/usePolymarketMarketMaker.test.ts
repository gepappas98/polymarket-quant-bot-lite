import { describe, expect, it } from "vitest";
import { applyPolymarketMarketMessage, bookMetrics, simulatePaperDepthFill } from "./usePolymarketMarketMaker";

describe("real Polymarket Market Maker data path", () => {
  it("normalizes a real book and exposes bid/ask/mid/spread/depth", () => {
    const book = applyPolymarketMarketMessage(null, {
      event_type: "book",
      asset_id: "token-1",
      timestamp: "1700000000000",
      bids: [{ price: "0.48", size: "10" }, { price: "0.49", size: "5" }],
      asks: [{ price: "0.52", size: "8" }, { price: "0.51", size: "2" }],
    }, "token-1");
    expect(book).not.toBeNull();
    expect(bookMetrics(book)).toMatchObject({ bestBid: 0.49, bestAsk: 0.51, mid: 0.5, bidDepth: 15, askDepth: 10 });
    expect(bookMetrics(book).spread).toBeCloseTo(0.02, 10);
  });

  it("applies price changes and deletes without inventing levels", () => {
    const book = applyPolymarketMarketMessage({ bids: [{ price: 0.49, shares: 5 }], asks: [{ price: 0.51, shares: 2 }], timestamp: "1" }, {
      event_type: "price_change", asset_id: "token-1", timestamp: "2", price_changes: [
        { asset_id: "token-1", price: "0.49", size: "0", side: "BUY" },
        { asset_id: "token-1", price: "0.52", size: "3", side: "SELL" },
      ],
    }, "token-1");
    expect(book?.bids).toEqual([]);
    expect(book?.asks).toEqual([{ price: 0.51, shares: 2 }, { price: 0.52, shares: 3 }]);
  });

  it("consumes actual depth and reports partial paper fills", () => {
    const fill = simulatePaperDepthFill({ bids: [], asks: [{ price: 0.5, shares: 10 }, { price: 0.6, shares: 5 }], timestamp: "1" }, "BUY", 8);
    expect(fill).toMatchObject({ sizeUsd: 8, shares: 15, price: 8 / 15, partial: false });
    const partial = simulatePaperDepthFill({ bids: [], asks: [{ price: 0.5, shares: 10 }], timestamp: "1" }, "BUY", 8,);
    expect(partial).toMatchObject({ sizeUsd: 5, shares: 10, partial: true });
  });

  it("does not create replacement prices when no book exists", () => {
    expect(bookMetrics(null)).toEqual({ bestBid: null, bestAsk: null, mid: null, spread: null, bidDepth: 0, askDepth: 0 });
    expect(simulatePaperDepthFill({ bids: [], asks: [], timestamp: null }, "BUY", 25)).toBeNull();
  });
});

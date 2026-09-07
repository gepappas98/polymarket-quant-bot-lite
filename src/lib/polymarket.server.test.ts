import { afterEach, describe, expect, it, vi } from "vitest";
import { getPolymarketBook, searchPolymarketMarkets } from "./polymarket.server";

afterEach(() => vi.restoreAllMocks());

describe("Polymarket server adapters", () => {
  it("normalizes a full CLOB L2 book with best-price ordering", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              timestamp: "1710000000000",
              bids: [
                { price: "0.48", size: "20" },
                { price: "0.49", size: "10" },
              ],
              asks: [
                { price: "0.52", size: "30" },
                { price: "0.51", size: "5" },
              ],
            }),
            { status: 200 },
          ),
      ),
    );

    const book = await getPolymarketBook("token-1", "market-1");
    expect(book.bids).toEqual([
      { price: 0.49, shares: 10 },
      { price: 0.48, shares: 20 },
    ]);
    expect(book.asks).toEqual([
      { price: 0.51, shares: 5 },
      { price: 0.52, shares: 30 },
    ]);
    expect(book.market).toBe("market-1");
  });

  it("normalizes Gamma market tokens", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify([
              {
                id: "market-1",
                slug: "btc-up",
                question: "Will BTC be up?",
                active: true,
                closed: false,
                clobTokenIds: ["up", "down"],
                outcomes: ["Up", "Down"],
                tokens: [
                  { token_id: "up", outcome: "Up" },
                  { token_id: "down", outcome: "Down" },
                ],
              },
            ]),
            { status: 200 },
          ),
      ),
    );

    const markets = await searchPolymarketMarkets("btc", 5);
    expect(markets[0]).toMatchObject({
      id: "market-1",
      slug: "btc-up",
      question: "Will BTC be up?",
    });
    expect(markets[0].tokens).toHaveLength(2);
  });
});

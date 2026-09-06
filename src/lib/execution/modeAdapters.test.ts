import { describe, expect, it } from "vitest";
import { BacktestAdapter, ShadowAdapter, assertLiveAdapter } from "./modeAdapters";

describe("execution mode adapters", () => {
  it("keeps backtest on the shared paper adapter path", async () => {
    const adapter = new BacktestAdapter({ BTC: { ask: 0.4, askShares: 10 } });
    const result = await adapter.placeOrder({ clientOrderId: "bt-1", market: "BTC", side: "UP", orderType: "MARKET", price: 0.4, sizeShares: 2 });
    expect(adapter.name).toBe("backtest");
    expect(result.fills[0]?.shares).toBe(2);
  });

  it("shadow mode never creates fills", async () => {
    const adapter = new ShadowAdapter();
    const result = await adapter.placeOrder({ clientOrderId: "shadow-1", market: "BTC", side: "UP", orderType: "MARKET", price: 0.4, sizeShares: 2 });
    expect(result.accepted).toBe(true);
    expect(result.fills).toEqual([]);
  });

  it("rejects simulation adapters for live mode", () => {
    expect(() => assertLiveAdapter(new ShadowAdapter())).toThrow(/explicit live venue adapter/);
  });
});

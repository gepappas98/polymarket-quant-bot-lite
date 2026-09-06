import { describe, expect, it } from "vitest";

import { ManualClock } from "./clock";
import { InvalidTransitionError, canTransition } from "./models";
import { PaperAdapter } from "./paperAdapter";
import {
  applyFill,
  applyPlaceResult,
  beginCancel,
  completeCancel,
  createOrder,
  reconcileOrder,
  transition,
} from "./orderExecutor";

const clock = () => new ManualClock("2026-01-01T00:00:00.000Z");

function baseOrder(size = 100) {
  return createOrder(
    {
      clientOrderId: "coid-1",
      market: "btc-up-or-down",
      side: "UP",
      orderType: "LIMIT",
      price: 0.5,
      sizeShares: size,
      mode: "paper",
    },
    clock(),
  );
}

describe("order state machine", () => {
  it("cannot jump from SUBMITTED to FILLED without fill accounting", () => {
    const c = clock();
    const submitted = transition(baseOrder(), "SUBMITTED", c);
    expect(canTransition("SUBMITTED", "FILLED")).toBe(true);
    // ...but the executor only reaches FILLED via applyFill, which requires shares.
    const { order } = applyFill(
      submitted,
      { fillId: "f1", price: 0.5, shares: 40, fee: 0, filledAt: c.isoNow() },
      c,
    );
    expect(order.status).toBe("PARTIALLY_FILLED");
    expect(order.filledShares).toBe(40);
  });

  it("rejects invalid transitions", () => {
    const c = clock();
    const filled = applyFill(
      transition(baseOrder(10), "SUBMITTED", c),
      { fillId: "f1", price: 0.4, shares: 10, fee: 0, filledAt: c.isoNow() },
      c,
    ).order;
    expect(filled.status).toBe("FILLED");
    expect(() => transition(filled, "SUBMITTED", c)).toThrow(InvalidTransitionError);
  });
});

describe("partial fills", () => {
  it("keeps VWAP, fees and remaining size", () => {
    const c = clock();
    let order = transition(baseOrder(), "SUBMITTED", c);
    order = applyFill(order, { fillId: "f1", price: 0.4, shares: 50, fee: 0.1, filledAt: c.isoNow() }, c).order;
    order = applyFill(order, { fillId: "f2", price: 0.6, shares: 50, fee: 0.1, filledAt: c.isoNow() }, c).order;
    expect(order.status).toBe("FILLED");
    expect(order.avgFillPrice).toBeCloseTo(0.5, 6);
    expect(order.feesPaid).toBeCloseTo(0.2, 6);
  });

  it("ignores duplicate fill ids", () => {
    const c = clock();
    let order = transition(baseOrder(), "SUBMITTED", c);
    const fill = { fillId: "f1", price: 0.5, shares: 30, fee: 0, filledAt: c.isoNow() };
    order = applyFill(order, fill, c).order;
    const second = applyFill(order, fill, c);
    expect(second.applied).toBe(false);
    expect(second.order.filledShares).toBe(30);
  });

  it("rejects over-fills", () => {
    const c = clock();
    const order = transition(baseOrder(10), "SUBMITTED", c);
    expect(() =>
      applyFill(order, { fillId: "f1", price: 0.5, shares: 11, fee: 0, filledAt: c.isoNow() }, c),
    ).toThrow(/Over-fill/);
  });
});

describe("adapter + reconciliation", () => {
  it("consumes multiple ask levels with VWAP and residual depth", async () => {
    const c = clock();
    const adapter = new PaperAdapter({ mkt: { asks: [{ price: 0.5, shares: 20 }, { price: 0.51, shares: 30 }, { price: 0.52, shares: 50 }] } }, c);
    const req = { clientOrderId: "l2-1", market: "mkt", side: "UP" as const, orderType: "MARKET" as const, price: 1, sizeShares: 100 };
    const result = await adapter.placeOrder(req);
    expect(result.fills.map((fill) => fill.shares)).toEqual([20, 30, 50]);
    expect(result.fills.map((fill) => fill.price)).toEqual([0.5, 0.51, 0.52]);
    expect(result.closed).toBe(true);
    const second = await adapter.placeOrder({ ...req, clientOrderId: "l2-2", sizeShares: 10 });
    expect(second.fills).toHaveLength(0);
    expect(second.closed).toBe(true);
  });

  it("consumes bid levels for sells", async () => {
    const c = clock();
    const adapter = new PaperAdapter({ mkt: { bids: [{ price: 0.49, shares: 10 }, { price: 0.48, shares: 20 }] } }, c);
    const result = await adapter.placeOrder({ clientOrderId: "l2-sell", market: "mkt", side: "UP", action: "SELL", orderType: "MARKET", price: 0, sizeShares: 25 });
    expect(result.fills.map((fill) => fill.shares)).toEqual([10, 15]);
    expect(result.fills.map((fill) => fill.price)).toEqual([0.49, 0.48]);
  });

  it("fills a market order through the adapter", async () => {
    const c = clock();
    const adapter = new PaperAdapter({ "btc-up-or-down": { ask: 0.52, feeBps: 10 } }, c);
    const order = createOrder(
      {
        clientOrderId: "m-1",
        market: "btc-up-or-down",
        side: "UP",
        orderType: "MARKET",
        price: 0.52,
        sizeShares: 100,
        mode: "paper",
      },
      c,
    );
    const result = await adapter.placeOrder({
      clientOrderId: "m-1",
      market: "btc-up-or-down",
      side: "UP",
      orderType: "MARKET",
      price: 0.52,
      sizeShares: 100,
    });
    const done = applyPlaceResult(order, result, c);
    expect(done.status).toBe("FILLED");
    expect(done.avgFillPrice).toBeCloseTo(0.52, 6);
    expect(done.feesPaid).toBeGreaterThan(0);
  });

  it("restart reconciliation does not duplicate fills", async () => {
    const c = clock();
    const adapter = new PaperAdapter({ mkt: { ask: 0.5, askShares: 60 } }, c);
    const req = {
      clientOrderId: "r-1",
      market: "mkt",
      side: "UP" as const,
      orderType: "LIMIT" as const,
      price: 0.5,
      sizeShares: 100,
    };
    let order = createOrder({ ...req, mode: "paper" }, c);
    order = applyPlaceResult(order, await adapter.placeOrder(req), c);
    expect(order.status).toBe("PARTIALLY_FILLED");
    expect(order.filledShares).toBe(60);

    // venue fills the rest while the app is down
    adapter.fillRemaining("r-1", 40, 0.5);

    const [snapshot] = await adapter.fetchOrders(["r-1"]);
    const first = reconcileOrder(order, snapshot!, c);
    expect(first.appliedFills).toBe(1);
    expect(first.order.status).toBe("FILLED");
    expect(first.order.filledShares).toBe(100);

    // reconciling again must be a no-op
    const second = reconcileOrder(first.order, snapshot!, c);
    expect(second.appliedFills).toBe(0);
    expect(second.order.filledShares).toBe(100);
  });

  it("idempotent re-submit returns the same venue order", async () => {
    const c = clock();
    const adapter = new PaperAdapter({ mkt: { ask: 0.5, askShares: 10 } }, c);
    const req = {
      clientOrderId: "dup-1",
      market: "mkt",
      side: "UP" as const,
      orderType: "LIMIT" as const,
      price: 0.5,
      sizeShares: 100,
    };
    const a = await adapter.placeOrder(req);
    const b = await adapter.placeOrder(req);
    expect(b.venueOrderId).toBe(a.venueOrderId);
    expect(b.fills.length).toBe(a.fills.length);
  });

  it("cancels a resting order", async () => {
    const c = clock();
    const adapter = new PaperAdapter({ mkt: { ask: 0.6 } }, c);
    const req = {
      clientOrderId: "c-1",
      market: "mkt",
      side: "DOWN" as const,
      orderType: "LIMIT" as const,
      price: 0.4,
      sizeShares: 50,
    };
    let order = createOrder({ ...req, mode: "paper" }, c);
    order = applyPlaceResult(order, await adapter.placeOrder(req), c);
    expect(order.status).toBe("SUBMITTED");
    order = beginCancel(order, c);
    const { cancelled } = await adapter.cancelOrder({ clientOrderId: "c-1", venueOrderId: order.venueOrderId });
    order = completeCancel(order, c, cancelled);
    expect(order.status).toBe("CANCELLED");
  });
});

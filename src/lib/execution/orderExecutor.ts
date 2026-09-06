/**
 * Sprint 2 — order executor core.
 *
 * Pure, storage-free reducer over an Order: applies fills idempotently, keeps
 * partial-fill accounting (filled shares, VWAP, fees), and derives the next
 * status through the state machine. Reconciliation replays venue fills through
 * the same path, so a restart can never duplicate a fill.
 */

import type { Fill, Order, OrderStatus } from "./models";
import { assertTransition, isTerminal, round6 } from "./models";
import type { PlaceOrderRequest, PlaceOrderResult, VenueOrderSnapshot } from "./adapter";
import type { Clock } from "./clock";

const EPS = 1e-6;

export function createOrder(
  req: PlaceOrderRequest & { mode: Order["mode"]; reason?: string | null },
  clock: Clock,
  id = req.clientOrderId,
): Order {
  const at = clock.isoNow();
  return {
    id,
    clientOrderId: req.clientOrderId,
    venueOrderId: null,
    market: req.market,
    side: req.side,
    orderType: req.orderType,
    mode: req.mode,
    price: req.price,
    sizeShares: req.sizeShares,
    filledShares: 0,
    avgFillPrice: 0,
    feesPaid: 0,
    status: "PENDING",
    reason: req.reason ?? null,
    error: null,
    createdAt: at,
    updatedAt: at,
    fills: [],
  };
}

export function transition(order: Order, to: OrderStatus, clock: Clock, error?: string): Order {
  if (order.status === to && to !== "PARTIALLY_FILLED") return order;
  assertTransition(order.status, to);
  return { ...order, status: to, error: error ?? order.error, updatedAt: clock.isoNow() };
}

/** Idempotent: a fillId already present is ignored. Over-fills are rejected. */
export function applyFill(order: Order, fill: Fill, clock: Clock): { order: Order; applied: boolean } {
  if (isTerminal(order.status) && order.status !== "FILLED") {
    // Late fill on a cancelled/expired order: still account for it if capacity remains.
    if (order.filledShares + fill.shares > order.sizeShares + EPS) return { order, applied: false };
  }
  if (order.fills.some((f) => f.fillId === fill.fillId)) return { order, applied: false };
  if (fill.shares <= 0) return { order, applied: false };
  if (order.filledShares + fill.shares > order.sizeShares + EPS) {
    throw new Error(
      `Over-fill rejected for ${order.clientOrderId}: ${order.filledShares}+${fill.shares} > ${order.sizeShares}`,
    );
  }

  const filledShares = round6(order.filledShares + fill.shares);
  const notional = order.avgFillPrice * order.filledShares + fill.price * fill.shares;
  const next: Order = {
    ...order,
    fills: [...order.fills, fill],
    filledShares,
    avgFillPrice: round6(notional / filledShares),
    feesPaid: round6(order.feesPaid + (fill.fee || 0)),
    updatedAt: clock.isoNow(),
  };
  const complete = filledShares >= order.sizeShares - EPS;
  const target: OrderStatus = complete ? "FILLED" : "PARTIALLY_FILLED";
  return {
    order: isTerminal(next.status) && !complete ? next : { ...next, status: nextStatus(next.status, target) },
    applied: true,
  };
}

function nextStatus(from: OrderStatus, to: OrderStatus): OrderStatus {
  assertTransition(from, to);
  return to;
}

export function applyPlaceResult(order: Order, result: PlaceOrderResult, clock: Clock): Order {
  if (!result.accepted) {
    return transition(order, "REJECTED", clock, result.rejectReason ?? "venue rejected order");
  }
  let next = transition({ ...order, venueOrderId: result.venueOrderId }, "SUBMITTED", clock);
  for (const fill of result.fills) next = applyFill(next, fill, clock).order;
  if (result.closed && next.status !== "FILLED" && !isTerminal(next.status)) {
    next = transition(next, next.filledShares > 0 ? "CANCELLED" : "EXPIRED", clock, "closed by venue");
  }
  return next;
}

/**
 * Startup / periodic reconciliation: fold every fill the venue knows about back
 * into the local order. Already-applied fills are skipped by fillId, so this is
 * safe to run repeatedly.
 */
export function reconcileOrder(
  order: Order,
  snapshot: VenueOrderSnapshot,
  clock: Clock,
): { order: Order; appliedFills: number } {
  let next: Order = order.venueOrderId ? order : { ...order, venueOrderId: snapshot.venueOrderId };
  let appliedFills = 0;
  if (next.status === "PENDING" && (snapshot.venueOrderId || snapshot.fills.length > 0)) {
    next = transition(next, "SUBMITTED", clock);
  }
  for (const fill of snapshot.fills) {
    const res = applyFill(next, fill, clock);
    next = res.order;
    if (res.applied) appliedFills += 1;
  }
  if (!snapshot.open && !isTerminal(next.status)) {
    if (snapshot.rejected) next = transition(next, "REJECTED", clock, "rejected at venue");
    else if (snapshot.cancelled || next.filledShares > 0) next = transition(next, "CANCELLED", clock, "closed at venue");
    else next = transition(next, "EXPIRED", clock, "no longer open at venue");
  }
  return { order: next, appliedFills };
}

export function beginCancel(order: Order, clock: Clock): Order {
  if (isTerminal(order.status)) return order;
  return transition(order, "CANCELLING", clock);
}

export function completeCancel(order: Order, clock: Clock, cancelled: boolean): Order {
  if (isTerminal(order.status)) return order;
  if (!cancelled) return transition(order, "FAILED", clock, "cancel rejected by venue");
  return transition(order, "CANCELLED", clock, "cancelled by user");
}

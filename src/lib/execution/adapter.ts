/**
 * Sprint 1/2 — exchange adapter interface.
 *
 * Every venue (Polymarket, paper, later replay) implements the same surface so
 * the order executor never knows which venue it talks to.
 */

import type { Fill, OrderSide, OrderType } from "./models";

export interface PlaceOrderRequest {
  clientOrderId: string;
  market: string;
  side: OrderSide;
  orderType: OrderType;
  price: number;
  sizeShares: number;
  action?: "BUY" | "SELL";
}

export interface PlaceOrderResult {
  accepted: boolean;
  venueOrderId: string | null;
  /** Fills the venue reported synchronously (market orders usually do). */
  fills: Fill[];
  /** Venue says the order is done and will send no further fills. */
  closed: boolean;
  rejectReason?: string;
}

export interface VenueOrderSnapshot {
  clientOrderId: string;
  venueOrderId: string | null;
  /** Everything the venue has ever filled for this order. */
  fills: Fill[];
  open: boolean;
  cancelled: boolean;
  rejected: boolean;
}

export interface ExchangeAdapter {
  readonly name: string;
  placeOrder(req: PlaceOrderRequest): Promise<PlaceOrderResult>;
  cancelOrder(ref: { clientOrderId: string; venueOrderId: string | null }): Promise<{ cancelled: boolean }>;
  /** Used by startup reconciliation — venue truth for a set of orders. */
  fetchOrders(clientOrderIds: string[]): Promise<VenueOrderSnapshot[]>;
}

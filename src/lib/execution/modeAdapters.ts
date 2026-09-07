import type { ExchangeAdapter, PlaceOrderRequest, PlaceOrderResult, VenueOrderSnapshot } from "./adapter";
import type { Fill } from "./models";
import { PaperAdapter, type PaperQuote } from "./paperAdapter";
import type { Clock } from "./clock";
import { systemClock } from "./clock";

export class BacktestAdapter extends PaperAdapter {
  override readonly name: string = "backtest";

  constructor(quotes: Record<string, PaperQuote>, clock: Clock = systemClock) {
    super(quotes, clock);
  }
}

/**
 * Shadow mode observes the same quote path but never reports financial fills.
 * It records order intent locally through the common adapter contract so the
 * order reducer can prove that no position or cash mutation occurred.
 */
export class ShadowAdapter implements ExchangeAdapter {
  readonly name = "shadow";
  private readonly orders = new Map<string, VenueOrderSnapshot>();

  async placeOrder(req: PlaceOrderRequest): Promise<PlaceOrderResult> {
    const snapshot: VenueOrderSnapshot = {
      clientOrderId: req.clientOrderId,
      venueOrderId: `shadow-${req.clientOrderId}`,
      fills: [],
      open: false,
      cancelled: false,
      rejected: false,
    };
    this.orders.set(req.clientOrderId, snapshot);
    return {
      accepted: true,
      venueOrderId: snapshot.venueOrderId,
      fills: [] as Fill[],
      closed: true,
    };
  }

  async cancelOrder(ref: { clientOrderId: string; venueOrderId: string | null }): Promise<{ cancelled: boolean }> {
    const order = this.orders.get(ref.clientOrderId);
    if (!order || !order.open) return { cancelled: false };
    order.open = false;
    order.cancelled = true;
    return { cancelled: true };
  }

  async fetchOrders(clientOrderIds: string[]): Promise<VenueOrderSnapshot[]> {
    return clientOrderIds.flatMap((id) => {
      const order = this.orders.get(id);
      return order ? [order] : [];
    });
  }
}

export function assertLiveAdapter(adapter: ExchangeAdapter): void {
  if (adapter.name === "paper" || adapter.name === "backtest" || adapter.name === "shadow") {
    throw new Error("Live mode requires an explicit live venue adapter; simulation cannot be used as live execution");
  }
}

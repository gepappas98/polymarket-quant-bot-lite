export type CopyActivitySource = "polymarket_data_api";
export type ObservedTraderActivity = {
  eventId: string;
  wallet: string;
  marketId: string;
  tokenId: string;
  market: string;
  side: "BUY" | "SELL";
  price: number | null;
  quantity: number | null;
  usdcSize: number | null;
  timestamp: string;
  source: CopyActivitySource;
  transactionHash: string | null;
};

export type CopyDecision =
  | { status: "ACCEPTED"; mode: "PAPER"; event: ObservedTraderActivity; reason?: never }
  | { status: "REJECTED"; mode?: never; event?: never; reason: "STALE_EVENT" | "MISSING_MARKET" | "INVALID_QUANTITY" | "RISK_REJECTED" | "LIVE_COPY_DISABLED" };

const WALLET_PATTERN = /^0x[a-fA-F0-9]{40}$/;
const MAX_ACTIVITY_AGE_MS = 120_000;

function finiteNumber(value: unknown): number | null {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function normalizeTraderActivity(raw: unknown, wallet: string, now = Date.now()): ObservedTraderActivity | null {
  if (!WALLET_PATTERN.test(wallet)) return null;
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const eventId = String(row["id"] ?? row["transactionHash"] ?? "").trim();
  const marketId = String(row["conditionId"] ?? row["condition_id"] ?? row["market"] ?? "").trim();
  const tokenId = String(row["asset"] ?? row["tokenId"] ?? row["token_id"] ?? "").trim();
  const market = String(row["slug"] ?? row["title"] ?? row["market"] ?? marketId).trim();
  const timestampValue = finiteNumber(row["timestamp"]);
  const timestamp = timestampValue === null ? "" : new Date(timestampValue < 10_000_000_000 ? timestampValue * 1000 : timestampValue).toISOString();
  const side = String(row["side"] ?? "").toUpperCase();
  if (!eventId || !marketId || !tokenId || !market || !timestamp || !["BUY", "SELL"].includes(side)) return null;
  const parsedTimestamp = new Date(timestamp).getTime();
  if (!Number.isFinite(parsedTimestamp) || parsedTimestamp > now + 30_000) return null;
  return {
    eventId,
    wallet: wallet.toLowerCase(),
    marketId,
    tokenId,
    market,
    side: side as "BUY" | "SELL",
    price: finiteNumber(row["price"]),
    quantity: finiteNumber(row["size"] ?? row["quantity"]),
    usdcSize: finiteNumber(row["usdcSize"] ?? row["usdc_size"]),
    timestamp,
    source: "polymarket_data_api",
    transactionHash: row["transactionHash"] ? String(row["transactionHash"]) : null,
  };
}

export function dedupeActivity(events: ObservedTraderActivity[]): ObservedTraderActivity[] {
  return [...new Map(events.map((event) => [`${event.wallet}:${event.source}:${event.eventId}`, event])).values()]
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
}

export function decideCopy(event: ObservedTraderActivity, now = Date.now(), options: { maxAgeMs?: number; maxNotionalUsd?: number; live?: boolean } = {}): CopyDecision {
  if (options.live) return { status: "REJECTED", reason: "LIVE_COPY_DISABLED" };
  const age = now - new Date(event.timestamp).getTime();
  if (!Number.isFinite(age) || age < -30_000 || age > (options.maxAgeMs ?? MAX_ACTIVITY_AGE_MS)) return { status: "REJECTED", reason: "STALE_EVENT" };
  if (event.quantity === null || event.quantity <= 0) return { status: "REJECTED", reason: "INVALID_QUANTITY" };
  if (event.price !== null && (event.price <= 0 || event.price >= 1)) return { status: "REJECTED", reason: "RISK_REJECTED" };
  const notional = event.usdcSize ?? (event.price === null ? null : event.quantity * event.price);
  if (notional === null || notional <= 0 || notional > (options.maxNotionalUsd ?? 100)) return { status: "REJECTED", reason: "RISK_REJECTED" };
  return { status: "ACCEPTED", mode: "PAPER", event };
}

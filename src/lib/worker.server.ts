/**
 * Server-only bridge that mirrors desk / paper fills into the Render worker's
 * ledger, so Control Room stats (daily P&L, session fills, open positions)
 * reflect trades placed from this app. Credentials never reach the browser.
 */

const DEFAULT_WORKER_BASE = "https://polymarket-quant-bot-lite-1.onrender.com";

function workerBase(): string {
  const raw =
    process.env["BOT_API_URL"] ??
    process.env["VITE_API_URL"] ??
    (process.env["BOT_STATUS_URL"] ?? "").replace(/\/api\/status\/?$/, "") ??
    "";
  return (raw || DEFAULT_WORKER_BASE).replace(/\/$/, "");
}

function workerToken(): string | undefined {
  return process.env["BOT_STATUS_API_TOKEN"] ?? process.env["BOT_API_TOKEN"] ?? undefined;
}

export interface WorkerMirrorResult {
  mirrored: boolean;
  reason?: string;
  workerStatus?: string;
  workerTradeId?: number | null;
}

export interface MirrorTradeInput {
  marketSlug: string;
  tokenId?: string;
  side: "UP" | "DOWN";
  price: number;
  sizeUsd: number;
  balance: number;
  category?: string;
}

/** Best-effort: a mirroring failure must never fail the local trade. */
export async function mirrorTradeToWorker(input: MirrorTradeInput): Promise<WorkerMirrorResult> {
  const token = workerToken();
  if (!token) return { mirrored: false, reason: "worker API token is not configured" };
  if (!(input.sizeUsd > 0) || !(input.price > 0)) {
    return { mirrored: false, reason: "non-positive size or price" };
  }
  // Confidence is derived from the traded price so the worker's Kelly sizing
  // stays consistent with the price this app actually filled at.
  const confidence = Math.min(0.99, Math.max(0.01, input.price));
  try {
    const res = await fetch(`${workerBase()}/api/trades/place`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "application/json",
        "X-API-Token": token,
        authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        market_slug: input.marketSlug,
        token_id: input.tokenId ?? input.marketSlug,
        side: input.side,
        price: input.price,
        confidence,
        balance: input.balance,
        ...(input.category ? { category: input.category } : {}),
      }),
    });
    if (!res.ok) return { mirrored: false, reason: `worker responded ${res.status}` };
    const json = (await res.json()) as { status?: string; trade_id?: number | null };
    return {
      mirrored: json.status === "filled",
      workerStatus: json.status ?? "unknown",
      workerTradeId: json.trade_id ?? null,
      ...(json.status === "filled" ? {} : { reason: `worker ${json.status ?? "no status"}` }),
    };
  } catch {
    return { mirrored: false, reason: "worker unreachable" };
  }
}

/** Push a closing price to the worker so it evaluates stops and realizes P&L. */
export async function mirrorPriceToWorker(
  workerTradeId: number,
  currentPrice: number,
): Promise<WorkerMirrorResult> {
  const token = workerToken();
  if (!token) return { mirrored: false, reason: "worker API token is not configured" };
  try {
    const res = await fetch(`${workerBase()}/api/trades/price`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "application/json",
        "X-API-Token": token,
        authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ trade_id: workerTradeId, current_price: currentPrice }),
    });
    if (!res.ok) return { mirrored: false, reason: `worker responded ${res.status}` };
    const json = (await res.json()) as { status?: string };
    return { mirrored: true, workerStatus: json.status ?? "unknown" };
  } catch {
    return { mirrored: false, reason: "worker unreachable" };
  }
}

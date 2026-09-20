/**
 * Server-only bridge that mirrors desk / paper fills into the Render worker's
 * ledger, so Control Room stats (daily P&L, session fills, open positions)
 * reflect trades placed from this app. Credentials never reach the browser.
 */

const DEFAULT_WORKER_BASE = "https://polymarket-quant-bot-lite-1.onrender.com";

/**
 * The worker sizes every order with Kelly: below this conviction it computes a
 * zero stake and rejects the order ("kelly size is zero"). We stop earlier and
 * report it as "no edge" instead of sending a trade that cannot be accepted.
 */
export const MIN_WORKER_CONVICTION = 0.55;

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

/** The worker only accepts a single credential header; sending both is rejected. */
function workerHeaders(token: string): Record<string, string> {
  return {
    "content-type": "application/json",
    accept: "application/json",
    authorization: `Bearer ${token}`,
  };
}

export interface WorkerMirrorResult {
  mirrored: boolean;
  reason?: string;
  workerStatus?: string;
  workerTradeId?: number | null;
  /** Conviction actually sent to the worker (or evaluated and rejected). */
  conviction?: number;
  /** True when we withheld the trade because conviction showed no edge. */
  noEdge?: boolean;
}

export interface MirrorTradeInput {
  marketSlug: string;
  tokenId?: string;
  side: "UP" | "DOWN";
  price: number;
  sizeUsd: number;
  balance: number;
  category?: string;
  /** Desk conviction in 0..1. Defaults to the traded price when not supplied. */
  conviction?: number;
}

/** Clamp a conviction into the range the worker's Kelly sizing accepts. */
export function normalizeConviction(value: number | undefined, price: number): number {
  const raw = typeof value === "number" && Number.isFinite(value) ? value : price;
  const scaled = raw > 1 ? raw / 100 : raw;
  return Math.min(0.99, Math.max(0.01, scaled));
}

/** Best-effort: a mirroring failure must never fail the local trade. */
export async function mirrorTradeToWorker(input: MirrorTradeInput): Promise<WorkerMirrorResult> {
  const token = workerToken();
  if (!token) return { mirrored: false, reason: "worker API token is not configured" };
  if (!(input.sizeUsd > 0) || !(input.price > 0)) {
    return { mirrored: false, reason: "non-positive size or price" };
  }
  const conviction = normalizeConviction(input.conviction, input.price);
  if (conviction < MIN_WORKER_CONVICTION) {
    return {
      mirrored: false,
      noEdge: true,
      conviction,
      reason: `no edge: conviction ${(conviction * 100).toFixed(0)}% is below the worker threshold of ${(MIN_WORKER_CONVICTION * 100).toFixed(0)}%`,
    };
  }
  try {
    const res = await fetch(`${workerBase()}/api/trades/place`, {
      method: "POST",
      headers: workerHeaders(token),
      body: JSON.stringify({
        market_slug: input.marketSlug,
        token_id: input.tokenId ?? input.marketSlug,
        side: input.side,
        price: input.price,
        confidence: conviction,
        balance: input.balance,
        ...(input.category ? { category: input.category } : {}),
      }),
    });
    if (!res.ok) return { mirrored: false, conviction, reason: `worker responded ${res.status}` };
    const json = (await res.json()) as {
      status?: string;
      trade_id?: number | null;
      reasons?: string[];
    };
    return {
      mirrored: json.status === "filled",
      workerStatus: json.status ?? "unknown",
      workerTradeId: json.trade_id ?? null,
      conviction,
      ...(json.status === "filled"
        ? {}
        : { reason: json.reasons?.[0] ?? `worker ${json.status ?? "no status"}` }),
    };
  } catch {
    return { mirrored: false, conviction, reason: "worker unreachable" };
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
      headers: workerHeaders(token),
      body: JSON.stringify({ trade_id: workerTradeId, current_price: currentPrice }),
    });
    if (!res.ok) return { mirrored: false, reason: `worker responded ${res.status}` };
    const json = (await res.json()) as { status?: string };
    return { mirrored: true, workerStatus: json.status ?? "unknown" };
  } catch {
    return { mirrored: false, reason: "worker unreachable" };
  }
}

// ------------------------------------------------------- portfolio metrics ---

export interface WorkerPortfolio {
  source: "worker";
  mode: string;
  /** Configured starting bankroll the worker sizes against (WORKER_BANKROLL_USD). */
  bankroll: number;
  /** Bankroll plus realized P&L, minus the cost of positions still open. */
  balance: number;
  /** Bankroll plus realized P&L plus the entry value of open positions. */
  equity: number;
  realizedPnl: number;
  dailyPnl: number;
  openPositions: number;
  openExposure: number;
  dailyLossLimit: number;
  liveTradingAllowed: boolean;
  generatedAt: string;
}

interface WorkerTradeRow {
  status?: string;
  size_usd?: number | null;
  pnl_usd?: number | null;
}

function bankroll(): number {
  const raw = Number(process.env["WORKER_BANKROLL_USD"] ?? "10000");
  return Number.isFinite(raw) && raw > 0 ? raw : 10_000;
}

/**
 * Derive balance / equity / open-position figures from what the worker actually
 * reports (status + its trade ledger). Nothing here is synthesized: the only
 * configured input is the starting bankroll.
 */
export async function fetchWorkerPortfolio(): Promise<WorkerPortfolio> {
  const token = workerToken();
  const headers: Record<string, string> = {
    accept: "application/json",
    ...(token ? { authorization: `Bearer ${token}` } : {}),
  };
  const base = workerBase();
  const [statusRes, tradesRes] = await Promise.all([
    fetch(`${base}/api/status`, { headers }),
    fetch(`${base}/api/trades/history?limit=1000`, { headers }),
  ]);
  if (!statusRes.ok) throw new Error(`worker status unavailable (${statusRes.status})`);
  const status = (await statusRes.json()) as {
    mode?: string;
    daily_pnl?: number;
    open_positions?: number;
    live_trading_allowed?: boolean;
    generated_at?: string;
    risk_config?: { daily_loss_limit?: number };
  };
  const trades: WorkerTradeRow[] = tradesRes.ok ? ((await tradesRes.json()) as WorkerTradeRow[]) : [];

  let realizedPnl = 0;
  let openExposure = 0;
  let openCount = 0;
  for (const row of trades) {
    const size = Number(row.size_usd ?? 0);
    if (row.status === "open") {
      openCount += 1;
      openExposure += Number.isFinite(size) ? size : 0;
    } else {
      const pnl = Number(row.pnl_usd ?? 0);
      if (Number.isFinite(pnl)) realizedPnl += pnl;
    }
  }
  const start = bankroll();
  realizedPnl = Math.round(realizedPnl * 100) / 100;
  openExposure = Math.round(openExposure * 100) / 100;
  return {
    source: "worker",
    mode: status.mode ?? "paper",
    bankroll: start,
    balance: Math.round((start + realizedPnl - openExposure) * 100) / 100,
    equity: Math.round((start + realizedPnl) * 100) / 100,
    realizedPnl,
    dailyPnl: Number(status.daily_pnl ?? 0),
    openPositions: Number(status.open_positions ?? openCount),
    openExposure,
    dailyLossLimit: Math.abs(Number(status.risk_config?.daily_loss_limit ?? 0)),
    liveTradingAllowed: status.live_trading_allowed === true,
    generatedAt: status.generated_at ?? new Date().toISOString(),
  };
}

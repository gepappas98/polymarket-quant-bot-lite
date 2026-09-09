import type { BotConfig, BotStatus, GateRow } from "./bot-types";

/** Shape returned by the FastAPI sidecar's GET /api/status (risk-oriented). */
export interface WorkerRiskStatus {
  mode?: string;
  live_trading_allowed?: boolean;
  daily_pnl?: number;
  open_positions?: number;
  active_strategies?: string[];
  generated_at?: string;
  circuit_breaker?: WorkerGate;
  time_window?: WorkerGate;
  category_exposure?: Record<string, { exposure?: number; ceiling?: number | null }>;
  risk_config?: Record<string, unknown>;
}

interface WorkerGate {
  name?: string;
  status?: string;
  reason?: string;
}

function num(v: unknown, fallback: number): number {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}

function gate(g: WorkerGate | undefined, fallbackName: string): GateRow | null {
  if (!g) return null;
  const status = (g.status ?? "").toUpperCase();
  return {
    name: g.name ?? fallbackName,
    allowed: status !== "BLOCKED" && status !== "TRIPPED" && status !== "FAIL",
    reason: g.reason ?? status.toLowerCase(),
  };
}

/** True when the payload looks like the sidecar's risk status rather than a full BotStatus. */
export function isWorkerRiskStatus(data: unknown): data is WorkerRiskStatus {
  if (!data || typeof data !== "object") return false;
  const d = data as Record<string, unknown>;
  return "circuit_breaker" in d || "risk_config" in d;
}

/**
 * Translate the sidecar's risk status into the dashboard's BotStatus shape.
 * Only fields the worker actually reports are populated; unreported collections
 * stay empty so nothing synthetic is displayed.
 */
export function adaptWorkerRiskStatus(raw: WorkerRiskStatus): BotStatus {
  const rc = raw.risk_config ?? {};
  const mode = raw.mode === "live" ? "live" : "paper";
  const generatedAt = raw.generated_at ? Date.parse(raw.generated_at) : Date.now();

  const config: BotConfig = {
    mode,
    assets: [],
    windows: [],
    maxOrderUsd: 0,
    maxMarketExposureUsd: num(rc["category_ceiling_politics"], 0),
    arbThreshold: 0,
    minDirectionalEdge: 0,
    dailyLossLimitUsd: Math.abs(num(rc["daily_loss_limit"], 0)),
    cooldownMinutes: Math.round(num(rc["cooldown_seconds"], 0) / 60),
    minTrackRecordWinPct: 0,
    minTrackRecordSamples: 0,
    preferMaker: false,
  };

  const gates: GateRow[] = [
    gate(raw.circuit_breaker, "circuit_breaker"),
    gate(raw.time_window, "time_window"),
  ].filter((g): g is GateRow => g !== null);

  const dailyPnl = num(raw.daily_pnl, 0);

  return {
    source: "worker",
    data_source: mode === "live" ? "REAL" : "PAPER",
    execution_mode: mode === "live" ? "LIVE" : "PAPER",
    market_data_source: mode === "live" ? "REAL" : "PAPER",
    is_simulated: mode !== "live",
    market_data_provider: "polymarket-quant-bot sidecar",
    generatedAt: Number.isFinite(generatedAt) ? generatedAt : Date.now(),
    uptimeSeconds: 0,
    liveTradingAllowed: raw.live_trading_allowed === true,
    config,
    session: {
      intents: 0,
      blocked: 0,
      fills: 0,
      totalUsd: 0,
      dryRunFills: 0,
      liveFills: 0,
    },
    trackRecord: { winRatePct: 0, sampleSize: 0, avgPnl: dailyPnl },
    pnlSeries: [{ ts: generatedAt || Date.now(), cumulativePnl: dailyPnl }],
    markets: [],
    gates,
    ledger: [],
    swarm: null,
  };
}

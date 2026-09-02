export type Mode = "paper" | "live";

export interface BotConfig {
  mode: Mode;
  assets: string[];
  windows: number[];
  maxOrderUsd: number;
  maxMarketExposureUsd: number;
  arbThreshold: number;
  minDirectionalEdge: number;
  dailyLossLimitUsd: number;
  cooldownMinutes: number;
  minTrackRecordWinPct: number;
  minTrackRecordSamples: number;
  preferMaker: boolean;
  swarmEnabled?: boolean;
  consensusThreshold?: number;
}

export interface MarketRow {
  slug: string;
  asset: string;
  windowMinutes: number;
  secondsToClose: number;
  upAsk: number;
  downAsk: number;
  upBid: number;
  downBid: number;
  exposureUsd: number;
  cooldownUntil: number | null;
  signal: "arb" | "up" | "down" | "flat";
  edge: number;
}

export interface GateRow {
  name: string;
  allowed: boolean;
  reason: string;
}

export interface LedgerRow {
  ts: number;
  kind: "intent" | "fill" | "outcome" | "kill";
  marketSlug: string;
  side: string | null;
  price: number | null;
  sizeUsd: number | null;
  reason: string;
  status: "open" | "blocked" | "filled" | "closed";
  dryRun: boolean;
  pnlUsd: number | null;
  setId?: string | null;
  consensus?: number | null;
  consensusOk?: boolean | null;
}

/** One module in the non-LLM swarm pipeline (from worker GET /status). */
export interface SwarmAgentRow {
  score: number | null;
  veto: boolean;
  reason: string;
}

export interface SwarmSnapshot {
  enabled: boolean;
  threshold: number;
  last: {
    ok?: boolean;
    consensus?: number;
    threshold?: number;
    detail?: string;
    veto_by?: string[];
    scores?: Record<string, SwarmAgentRow>;
  } | null;
  agents: Record<string, SwarmAgentRow>;
  weights: Record<string, number>;
}

export interface BotStatus {
  source: "worker" | "demo";
  generatedAt: number;
  uptimeSeconds: number;
  liveTradingAllowed: boolean;
  config: BotConfig;
  session: {
    intents: number;
    blocked: number;
    fills: number;
    totalUsd: number;
    dryRunFills: number;
    liveFills: number;
  };
  trackRecord: { winRatePct: number; sampleSize: number; avgPnl: number };
  pnlSeries: { ts: number; cumulativePnl: number }[];
  markets: MarketRow[];
  gates: GateRow[];
  ledger: LedgerRow[];
  /** Present when worker runs v0.5+ swarm; demo feed synthesizes a snapshot. */
  swarm?: SwarmSnapshot;
}

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
}

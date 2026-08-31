import { lazy, type ComponentType } from "react";

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface StrategyParams {
  [key: string]: number;
}

export interface SimTrade {
  time: number;
  side: "BUY" | "SELL";
  price: number;
  pnl: number;
}

export interface SimResult {
  trades: SimTrade[];
  pnl: number;
  winRate: number;
  equityCurve: { time: number; equity: number }[];
}

export interface StrategyPlugin {
  id: string;
  name: string;
  description: string;
  defaults: StrategyParams;
  /** Lazily loaded parameter editor — code-split per strategy. */
  Panel: ComponentType<{
    params: StrategyParams;
    onChange: (next: StrategyParams) => void;
  }>;
  simulate: (candles: Candle[], params: StrategyParams) => SimResult;
}

function runLongOnly(
  candles: Candle[],
  signal: (i: number, candles: Candle[], p: StrategyParams) => "buy" | "sell" | "hold",
  params: StrategyParams,
): SimResult {
  const stake = params["stakeUsd"] ?? 100;
  let entry: number | null = null;
  let equity = 0;
  let wins = 0;
  const trades: SimTrade[] = [];
  const equityCurve: { time: number; equity: number }[] = [];

  for (let i = 0; i < candles.length; i++) {
    const c = candles[i]!;
    const s = signal(i, candles, params);
    if (s === "buy" && entry === null) {
      entry = c.close;
      trades.push({ time: c.time, side: "BUY", price: c.close, pnl: 0 });
    } else if (s === "sell" && entry !== null) {
      const pnl = ((c.close - entry) / entry) * stake;
      equity += pnl;
      if (pnl > 0) wins += 1;
      trades.push({ time: c.time, side: "SELL", price: c.close, pnl });
      entry = null;
    }
    equityCurve.push({ time: c.time, equity: Math.round(equity * 100) / 100 });
  }

  const closed = trades.filter((t) => t.side === "SELL").length;
  return {
    trades,
    pnl: Math.round(equity * 100) / 100,
    winRate: closed ? Math.round((1000 * wins) / closed) / 10 : 0,
    equityCurve,
  };
}

function sma(candles: Candle[], i: number, n: number): number | null {
  if (i + 1 < n) return null;
  let sum = 0;
  for (let k = i - n + 1; k <= i; k++) sum += candles[k]!.close;
  return sum / n;
}

export const strategies: StrategyPlugin[] = [
  {
    id: "momentum",
    name: "Momentum breakout",
    description: "Buys when fast SMA crosses above slow SMA, exits on the reverse cross.",
    defaults: { fast: 5, slow: 20, stakeUsd: 100 },
    Panel: lazy(() => import("./MomentumParams")),
    simulate: (candles, params) =>
      runLongOnly(
        candles,
        (i, cs, p) => {
          const f = sma(cs, i, p["fast"] ?? 5);
          const s = sma(cs, i, p["slow"] ?? 20);
          const fPrev = sma(cs, i - 1, p["fast"] ?? 5);
          const sPrev = sma(cs, i - 1, p["slow"] ?? 20);
          if (f === null || s === null || fPrev === null || sPrev === null) return "hold";
          if (fPrev <= sPrev && f > s) return "buy";
          if (fPrev >= sPrev && f < s) return "sell";
          return "hold";
        },
        params,
      ),
  },
  {
    id: "mean_reversion",
    name: "Mean reversion",
    description: "Buys dips below the SMA by a threshold, sells back at the mean.",
    defaults: { lookback: 20, thresholdPct: 1, stakeUsd: 100 },
    Panel: lazy(() => import("./MeanReversionParams")),
    simulate: (candles, params) =>
      runLongOnly(
        candles,
        (i, cs, p) => {
          const mean = sma(cs, i, p["lookback"] ?? 20);
          if (mean === null) return "hold";
          const dev = ((cs[i]!.close - mean) / mean) * 100;
          if (dev <= -(p["thresholdPct"] ?? 1)) return "buy";
          if (dev >= 0) return "sell";
          return "hold";
        },
        params,
      ),
  },
];

export function getStrategy(id: string): StrategyPlugin | undefined {
  return strategies.find((s) => s.id === id);
}

import type { BotStatus, LedgerRow, MarketRow } from "./bot-types";

/**
 * Deterministic-ish demo status generator. Used when no BOT_STATUS_URL worker
 * endpoint is configured, so the dashboard is always readable.
 */
function seeded(seed: number) {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

const ASSETS = ["BTC", "ETH", "SOL"];

function buildMarkets(rand: () => number, now: number): MarketRow[] {
  const rows: MarketRow[] = [];
  for (const asset of ASSETS) {
    for (const w of [5, 15]) {
      const upAsk = 0.35 + rand() * 0.3;
      const downAsk = Math.min(0.98, Math.max(0.02, 1 - upAsk + (rand() - 0.5) * 0.05));
      const sum = upAsk + downAsk;
      const edge = 0.5 - upAsk;
      const signal: MarketRow["signal"] =
        sum <= 0.985 ? "arb" : edge > 0.03 ? "up" : edge < -0.03 ? "down" : "flat";
      const cooling = rand() > 0.72;
      rows.push({
        slug: `${asset.toLowerCase()}-up-or-down-${w}m-${new Date(now).toISOString().slice(11, 16).replace(":", "")}`,
        asset,
        windowMinutes: w,
        secondsToClose: Math.floor(rand() * w * 60),
        upAsk,
        downAsk,
        upBid: Math.max(0.01, upAsk - 0.01 - rand() * 0.02),
        downBid: Math.max(0.01, downAsk - 0.01 - rand() * 0.02),
        exposureUsd: Math.round(rand() * 140),
        cooldownUntil: cooling ? now + Math.floor(rand() * 180_000) : null,
        signal,
        edge,
      });
    }
  }
  return rows;
}

function buildLedger(rand: () => number, now: number): LedgerRow[] {
  const kinds: LedgerRow["kind"][] = ["intent", "fill", "intent", "outcome", "intent"];
  const rows: LedgerRow[] = [];
  for (let i = 0; i < 22; i++) {
    const kind = kinds[Math.floor(rand() * kinds.length)]!;
    const asset = ASSETS[Math.floor(rand() * ASSETS.length)]!;
    const blocked = kind === "intent" && rand() > 0.62;
    const side = kind === "outcome" ? (rand() > 0.5 ? "UP" : "DOWN") : rand() > 0.5 ? "UP" : "DOWN";
    rows.push({
      ts: now - i * (35_000 + Math.floor(rand() * 40_000)),
      kind,
      marketSlug: `${asset.toLowerCase()}-up-or-down-${rand() > 0.5 ? 5 : 15}m`,
      side,
      price: kind === "outcome" ? null : Number((0.3 + rand() * 0.4).toFixed(3)),
      sizeUsd: kind === "outcome" ? null : Number((5 + rand() * 20).toFixed(2)),
      reason: blocked
        ? `BLOCKED: cooldown active until ${new Date(now + 60_000).toISOString().slice(11, 19)}`
        : kind === "outcome"
          ? "window resolved"
          : rand() > 0.5
            ? "complete-set arb: up_ask+down_ask <= threshold"
            : "directional edge tilt + inventory pair",
      status: blocked ? "blocked" : kind === "fill" ? "filled" : kind === "outcome" ? "closed" : "open",
      dryRun: true,
      pnlUsd: kind === "outcome" ? Number(((rand() - 0.42) * 9).toFixed(2)) : null,
    });
  }
  return rows.sort((a, b) => b.ts - a.ts);
}

export function buildDemoStatus(now = Date.now()): BotStatus {
  const rand = seeded(Math.floor(now / 15_000));
  const markets = buildMarkets(rand, now);
  const ledger = buildLedger(rand, now);

  let cum = 0;
  const pnlSeries = Array.from({ length: 40 }, (_, i) => {
    cum += (rand() - 0.44) * 4;
    return { ts: now - (39 - i) * 900_000, cumulativePnl: Number(cum.toFixed(2)) };
  });

  const outcomes = ledger.filter((r) => r.kind === "outcome");
  const wins = outcomes.filter((r) => (r.pnlUsd ?? 0) > 0).length;
  const fills = ledger.filter((r) => r.kind === "fill");
  const intents = ledger.filter((r) => r.kind === "intent");

  return {
    source: "demo",
    generatedAt: now,
    uptimeSeconds: 4 * 3600 + 812,
    liveTradingAllowed: false,
    config: {
      mode: "paper",
      assets: ASSETS,
      windows: [5, 15],
      maxOrderUsd: 25,
      maxMarketExposureUsd: 150,
      arbThreshold: 0.985,
      minDirectionalEdge: 0.03,
      dailyLossLimitUsd: -200,
      cooldownMinutes: 3,
      minTrackRecordWinPct: 48,
      minTrackRecordSamples: 12,
      preferMaker: true,
    },
    session: {
      intents: intents.length,
      blocked: intents.filter((r) => r.status === "blocked").length,
      fills: fills.length,
      totalUsd: Number(fills.reduce((a, r) => a + (r.sizeUsd ?? 0), 0).toFixed(2)),
      dryRunFills: fills.length,
      liveFills: 0,
    },
    trackRecord: {
      winRatePct: outcomes.length ? Number(((100 * wins) / outcomes.length).toFixed(1)) : 0,
      sampleSize: outcomes.length,
      avgPnl: outcomes.length
        ? Number((outcomes.reduce((a, r) => a + (r.pnlUsd ?? 0), 0) / outcomes.length).toFixed(2))
        : 0,
    },
    pnlSeries,
    markets,
    gates: [
      { name: "Live trading double opt-in", allowed: false, reason: "MODE is not live (paper/safe)" },
      { name: "Daily loss kill-switch", allowed: true, reason: "session pnl above -200 USD limit" },
      { name: "Order size limit", allowed: true, reason: "max 25 USD per order" },
      { name: "Market exposure cap", allowed: true, reason: "max 150 USD per market" },
      {
        name: "Track-record gate (directional)",
        allowed: outcomes.length >= 12,
        reason: outcomes.length >= 12 ? "win-rate above 48%" : "sample size below 12 outcomes — fail closed",
      },
      { name: "Per-market cooldown", allowed: true, reason: "3 min lock after each admitted intent" },
    ],
    ledger,
  };
}

/** Fetch status from a running worker, if one is configured. */
export async function fetchWorkerStatus(): Promise<BotStatus> {
  const url = process.env["BOT_STATUS_URL"];
  if (!url) return buildDemoStatus();
  try {
    const res = await fetch(url, { headers: { accept: "application/json" } });
    if (!res.ok) throw new Error(`worker responded ${res.status}`);
    const data = (await res.json()) as Partial<BotStatus>;
    return { ...buildDemoStatus(), ...data, source: "worker" };
  } catch {
    return buildDemoStatus();
  }
}

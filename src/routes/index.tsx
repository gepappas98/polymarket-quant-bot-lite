import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { getBotStatus } from "@/lib/bot.functions";
import { NavLinks } from "@/components/dashboard/NavLinks";
import { SimulateTradeWidget } from "@/components/dashboard/SimulateTradeWidget";
import { SwarmAgentsPanel } from "@/components/dashboard/SwarmAgentsPanel";
import { getRiskGates, riskQueryKeys } from "@/lib/riskApi";

import {
  ConfigPanel,
  GatesPanel,
  LedgerFeed,
  MarketsTable,
  PnlChart,
  StatTile,
  SupportPanel,
  usd,
} from "@/components/dashboard/Panels";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Polymarket Quant Bot — Control Room" },
      {
        name: "description",
        content:
          "Live monitoring for a short-window Polymarket Up/Down worker: markets, arb spreads, safety gates, ledger and paper P&L.",
      },
      { property: "og:title", content: "Polymarket Quant Bot — Control Room" },
      {
        property: "og:description",
        content: "Markets, arb spreads, safety gates, ledger and paper P&L for the trading worker.",
      },
    ],
  }),
  component: Dashboard,
});

function uptime(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function Dashboard() {
  const fetchStatus = useServerFn(getBotStatus);
  const { data, isLoading } = useQuery({
    queryKey: ["bot-status"],
    queryFn: () => fetchStatus(),
    refetchInterval: 10_000,
  });
  const riskGates = useQuery({
    queryKey: riskQueryKeys.gates(),
    queryFn: () => getRiskGates(),
    refetchInterval: 10_000,
  });

  if (isLoading || !data) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="label-caps">Connecting to worker…</p>
      </main>
    );
  }

  const { config, session, trackRecord } = data;
  const lastPnl = data.pnlSeries[data.pnlSeries.length - 1]?.cumulativePnl ?? 0;
  const blockRate = session.intents ? (100 * session.blocked) / session.intents : 0;

  return (
    <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-10">
      <header className="panel mb-6 flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-4">
        <div>
          <h1 className="text-lg font-bold tracking-tight sm:text-xl">Polymarket Quant Bot</h1>
          <p className="tape mt-1 text-[11px] text-muted-foreground">
            short-window crypto Up/Down · complete-set arb + inventory
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <NavLinks />
          <span
            className={`tape flex items-center gap-2 rounded border px-2 py-1 text-[10px] uppercase ${
              config.mode === "live"
                ? "border-down/50 bg-down/15 text-down"
                : "border-up/50 bg-up/15 text-up"
            }`}
          >
            <span className="live-dot size-1.5 rounded-full bg-current" />
            {config.mode === "live" ? "live money" : "paper mode"}
          </span>
          <span className="tape rounded border border-border bg-muted px-2 py-1 text-[10px] uppercase text-muted-foreground">
            {data.source === "worker" ? "worker feed" : "demo feed"}
          </span>
          <span className="tape rounded border border-border bg-muted px-2 py-1 text-[10px] uppercase text-muted-foreground">
            up {uptime(data.uptimeSeconds)}
          </span>
          <Link
            to="/desk"
            className="tape rounded border border-primary/50 bg-primary/15 px-2 py-1 text-[10px] uppercase text-primary"
          >
            trading desk
          </Link>
        </div>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Session P&L"
          value={usd(lastPnl)}
          sub={`limit ${usd(config.dailyLossLimitUsd)}`}
          tone={lastPnl >= 0 ? "up" : "down"}
        />
        <StatTile
          label="Fills"
          value={String(session.fills)}
          sub={`${usd(session.totalUsd)} notional · ${session.liveFills} live`}
        />
        <StatTile
          label="Blocked intents"
          value={`${session.blocked}/${session.intents}`}
          sub={`${blockRate.toFixed(0)}% gated`}
          tone={blockRate > 50 ? "warn" : "default"}
        />
        <StatTile
          label="Win rate"
          value={`${trackRecord.winRatePct}%`}
          sub={`${trackRecord.sampleSize} outcomes · avg ${usd(trackRecord.avgPnl)}`}
          tone={trackRecord.winRatePct >= config.minTrackRecordWinPct ? "up" : "warn"}
        />
      </div>

      <div className="mt-3">
        <SwarmAgentsPanel swarm={data.swarm} />
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-2">
          <MarketsTable markets={data.markets} arbThreshold={config.arbThreshold} />
          <PnlChart series={data.pnlSeries} />
          <GatesPanel
            gates={data.gates}
            extra={
              riskGates.data
                ? {
                    ...(riskGates.data.gates.find((gate) => gate.name === "time_window")
                      ? {
                          timeWindow: riskGates.data.gates.find(
                            (gate) => gate.name === "time_window",
                          ),
                        }
                      : {}),
                    trailingStops: riskGates.data.trailing_stops,
                    categoryExposure: riskGates.data.category_exposure,
                  }
                : undefined
            }
          />
          <SimulateTradeWidget />
        </div>
        <div className="space-y-3">
          <LedgerFeed rows={data.ledger} />
          <ConfigPanel config={config} />
        </div>
      </div>

      <div className="mt-3">
        <SupportPanel />
      </div>

      <footer className="tape mt-6 text-[10px] leading-relaxed text-muted-foreground">
        Educational software. Not financial advice — paper trade first. Set{" "}
        <code className="rounded bg-muted px-1 py-0.5">BOT_STATUS_URL</code> to point this dashboard
        at a running worker; otherwise a demo feed is shown.
      </footer>
    </main>
  );
}

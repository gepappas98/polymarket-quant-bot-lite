import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { getBotStatus } from "@/lib/bot.functions";
import { NavLinks } from "@/components/dashboard/NavLinks";
import { SimulateTradeWidget } from "@/components/dashboard/SimulateTradeWidget";
import { SwarmAgentsPanel } from "@/components/dashboard/SwarmAgentsPanel";
import { getMarketsSnapshot, getRiskGates, riskQueryKeys, analyticsQueryKeys } from "@/lib/riskApi";
import { MarketSnapshot } from "@/components/dashboard/AnalyticsPanels";
import {
  MetricCards,
  SystemStatusBar,
  useMetricsSummary,
} from "@/components/dashboard/MetricCards";

import {
  ConfigPanel,
  GatesPanel,
  LedgerFeed,
  MarketsTable,
  PnlChart,
  SupportPanel,
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

/**
 * Never rejects. Reads the stable server route (see routes/api/public/bot-status.ts)
 * and degrades to client-side demo data if the transport itself fails, so a
 * deployment-level RPC/route failure can no longer blank the Control Room.
 */
async function loadStatus(): Promise<BotStatus> {
  try {
    const res = await fetch("/api/public/bot-status", {
      headers: { accept: "application/json" },
    });
    if (!res.ok) throw new Error(`status endpoint returned ${res.status}`);
    const data = (await res.json()) as BotStatus;
    if (!data || typeof data !== "object" || !data.config) {
      throw new Error("status endpoint returned an unexpected payload");
    }
    return data;
  } catch (err) {
    const demo = buildDemoStatus();
    demo.status_error = err instanceof Error ? err.message : "worker status unavailable";
    return demo;
  }
}

function Dashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["bot-status"],
    queryFn: loadStatus,
    refetchInterval: 10_000,
    retry: 1,
  });
  const summary = useMetricsSummary();
  const snapshot = useQuery({
    queryKey: analyticsQueryKeys.snapshot(),
    queryFn: () => getMarketsSnapshot(),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
  const riskGates = useQuery({
    queryKey: riskQueryKeys.gates(),
    queryFn: () => getRiskGates(),
    refetchInterval: 10_000,
  });

  if (isLoading && !data) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="label-caps">Connecting to worker…</p>
      </main>
    );
  }

  const status = data ?? buildDemoStatus();
  const { config } = status;


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
            {status.data_source === "REAL" ? "LIVE MARKET DATA" : `${status.data_source} DATA`}
          </span>
          <span className="tape rounded border border-border bg-muted px-2 py-1 text-[10px] uppercase text-muted-foreground">
            up {uptime(status.uptimeSeconds)}
          </span>
          <Link
            to="/desk"
            className="tape rounded border border-primary/50 bg-primary/15 px-2 py-1 text-[10px] uppercase text-primary"
          >
            trading desk
          </Link>
        </div>
      </header>

      {status.data_source === "DEMO" ? (
        <div className="panel mb-3 border-down/50 bg-down/10 px-4 py-3">
          <p className="text-sm font-semibold text-down">DEMO DATA</p>
          <p className="tape mt-1 text-[11px] text-muted-foreground">
            These values are synthetic and read-only. They are not Polymarket observations or worker
            results.
          </p>
          {status.status_error ? (
            <p className="tape mt-1 text-[11px] text-muted-foreground">
              Worker status unavailable: {status.status_error}. Read-only demo until the worker
              responds.
            </p>
          ) : null}
        </div>
      ) : null}

      <SystemStatusBar summary={summary.data} fallbackMode={config.mode} />
      <MetricCards summary={summary.data} />

      {snapshot.data ? (
        <div className="mt-3">
          <MarketSnapshot markets={snapshot.data} />
        </div>
      ) : null}

      <div className="mt-3">
        <SwarmAgentsPanel swarm={status.swarm} />
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-2">
          <MarketsTable markets={status.markets} arbThreshold={config.arbThreshold} />
          <PnlChart series={status.pnlSeries} />
          <GatesPanel
            gates={status.gates}
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
          <LedgerFeed rows={status.ledger} />
          <ConfigPanel config={config} />
        </div>
      </div>

      <div className="mt-3">
        <SupportPanel />
      </div>

      <footer className="tape mt-6 text-[10px] leading-relaxed text-muted-foreground">
        Educational software. Not financial advice — paper trade first. Data provenance is shown
        explicitly; demo values are never presented as live worker status.
      </footer>
    </main>
  );
}

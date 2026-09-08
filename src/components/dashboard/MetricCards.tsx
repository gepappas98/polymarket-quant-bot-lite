import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, ArrowDownRight, ArrowUpRight, Gauge, Layers, ShieldAlert } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { analyticsQueryKeys, getMetricsSummary, type MetricsSummary } from "@/lib/riskApi";
import { usd } from "@/components/dashboard/Panels";

const STATUS = {
  active: {
    label: "SYSTEM ACTIVE",
    className: "border-up/50 bg-up/15 text-up",
    Icon: Activity,
  },
  paper: {
    label: "PAPER MODE",
    className: "border-warn/50 bg-warn/15 text-warn",
    Icon: Layers,
  },
  demo: {
    label: "DEMO MODE",
    className: "border-down/50 bg-down/15 text-down",
    Icon: ShieldAlert,
  },
  paused: {
    label: "SYSTEM PAUSED",
    className: "border-down/50 bg-down/15 text-down",
    Icon: ShieldAlert,
  },
} as const;

function useUtcClock() {
  const [now, setNow] = useState<string>("");
  useEffect(() => {
    const tick = () => setNow(new Date().toISOString().slice(11, 19));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

export function useMetricsSummary() {
  return useQuery({
    queryKey: analyticsQueryKeys.summary(),
    queryFn: () => getMetricsSummary(),
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
}

export function SystemStatusBar({
  summary,
  fallbackMode,
  dataSource,
}: {
  summary?: MetricsSummary | undefined;
  fallbackMode?: string | undefined;
  dataSource?: string | undefined;
}) {
  const clock = useUtcClock();
  const key = (dataSource === "DEMO"
    ? "demo"
    : summary?.system_status ??
      (fallbackMode === "live" ? "active" : "paper")) as keyof typeof STATUS;
  const state = STATUS[key] ?? STATUS.paper;
  const { Icon } = state;
  return (
    <div
      className={`mb-3 flex flex-wrap items-center gap-3 rounded-md border px-4 py-2.5 ${state.className}`}
      role="status"
    >
      <Icon className="size-4" aria-hidden />
      <span className="tape text-[11px] font-semibold uppercase tracking-widest">
        {state.label}
      </span>
      <span className="ml-auto tape text-[11px] opacity-80">{clock ? `${clock} UTC` : "—"}</span>
    </div>
  );
}

function Card({
  label,
  value,
  sub,
  tone = "default",
  children,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "default" | "up" | "down" | "warn";
  children?: React.ReactNode;
}) {
  const toneClass =
    tone === "up"
      ? "text-up"
      : tone === "down"
        ? "text-down"
        : tone === "warn"
          ? "text-warn"
          : "text-foreground";
  return (
    <section className="panel px-4 py-3">
      <div className="label-caps flex items-center gap-2">
        <Gauge className="size-3 opacity-50" aria-hidden />
        {label}
      </div>
      <div className={`tape mt-2 text-xl font-semibold ${toneClass}`}>{value}</div>
      {sub ? <div className="tape mt-1 text-[10px] text-muted-foreground">{sub}</div> : null}
      {children}
    </section>
  );
}

export function MetricCards({ summary }: { summary?: MetricsSummary | undefined }) {
  const source = summary?.data_source ?? "UNAVAILABLE";
  const hasData = Boolean(summary);
  const lossUsed = summary?.daily_loss_used ?? 0;
  const lossLimit = summary?.daily_loss_limit ?? 0;
  const usedPct = lossLimit > 0 ? Math.min(100, (100 * lossUsed) / lossLimit) : 0;
  const change = summary?.daily_pnl_change ?? 0;
  const provenance = `source: ${source}`;

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Card
        label="Price / Stock"
        value={hasData && summary?.current_price != null ? `$${summary.current_price.toFixed(3)}` : "NO DATA"}
        sub={summary?.top_market ? `top volume · ${summary.top_market} · ${provenance}` : provenance}
      />
      <Card
        label="Trades / wk"
        value={hasData ? String(summary?.weekly_trades) : "NO DATA"}
        sub={hasData ? `${usd(summary?.weekly_volume ?? 0)} USDC notional · ${provenance}` : provenance}
      />
      <Card
        label="STL / day"
        value={hasData ? `${usd(lossUsed)} / ${usd(lossLimit)}` : "NO DATA"}
        sub={hasData ? `${usedPct.toFixed(0)}% of daily stop-loss used · ${provenance}` : provenance}
        tone={usedPct > 75 ? "down" : usedPct > 40 ? "warn" : "default"}
      >
        {hasData ? <Progress className="mt-3 h-1.5" value={usedPct} /> : null}
      </Card>
      <Card
        label="Change in value"
        value={hasData ? `${change >= 0 ? "+" : ""}${usd(change)}` : "NO DATA"}
        sub={hasData ? `${summary?.daily_pnl_percent.toFixed(2)}% today · ${summary?.closed_today} closed · ${provenance}` : provenance}
        tone={hasData && change < 0 ? "down" : "up"}
      >
        {hasData ? (
          <div className="tape mt-2 flex items-center gap-1 text-[10px]">
            {change >= 0 ? (
              <ArrowUpRight className="size-3 text-up" aria-hidden />
            ) : (
              <ArrowDownRight className="size-3 text-down" aria-hidden />
            )}
            <span className="text-muted-foreground">{summary?.open_positions ?? 0} open positions</span>
          </div>
        ) : null}
      </Card>
    </div>
  );
}

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
}: {
  summary?: MetricsSummary | undefined;
  fallbackMode?: string | undefined;
}) {
  const clock = useUtcClock();
  const key = (summary?.system_status ??
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
  const lossUsed = summary?.daily_loss_used ?? 0;
  const lossLimit = summary?.daily_loss_limit ?? 0;
  const usedPct = lossLimit > 0 ? Math.min(100, (100 * lossUsed) / lossLimit) : 0;
  const change = summary?.daily_pnl_change ?? 0;

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Card
        label="Price / Stock"
        value={summary?.current_price != null ? `$${summary.current_price.toFixed(3)}` : "—"}
        sub={summary?.top_market ? `top volume · ${summary.top_market}` : "no fills yet"}
      />
      <Card
        label="Trades / wk"
        value={String(summary?.weekly_trades ?? 0)}
        sub={`${usd(summary?.weekly_volume ?? 0)} USDC notional`}
      />
      <Card
        label="STL / day"
        value={`${usd(lossUsed)} / ${usd(lossLimit)}`}
        sub={`${usedPct.toFixed(0)}% of daily stop-loss used`}
        tone={usedPct > 75 ? "down" : usedPct > 40 ? "warn" : "default"}
      >
        <Progress className="mt-3 h-1.5" value={usedPct} />
      </Card>
      <Card
        label="Change in value"
        value={`${change >= 0 ? "+" : ""}${usd(change)}`}
        sub={`${summary?.daily_pnl_percent?.toFixed(2) ?? "0.00"}% today · ${summary?.closed_today ?? 0} closed`}
        tone={change >= 0 ? "up" : "down"}
      >
        <div className="tape mt-2 flex items-center gap-1 text-[10px]">
          {change >= 0 ? (
            <ArrowUpRight className="size-3 text-up" aria-hidden />
          ) : (
            <ArrowDownRight className="size-3 text-down" aria-hidden />
          )}
          <span className="text-muted-foreground">
            {summary?.open_positions ?? 0} open positions
          </span>
        </div>
      </Card>
    </div>
  );
}

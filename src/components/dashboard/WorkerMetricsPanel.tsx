import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { Coins, Gauge, LineChart, Layers } from "lucide-react";

import { getDeskConviction } from "@/lib/paper.functions";

interface WorkerPortfolio {
  mode: string;
  bankroll: number;
  balance: number;
  equity: number;
  realizedPnl: number;
  dailyPnl: number;
  openPositions: number;
  openExposure: number;
  dailyLossLimit: number;
  generatedAt: string;
}

const money = (n: number) => `${n < 0 ? "-" : ""}$${Math.abs(n).toFixed(2)}`;

function Tile({
  label,
  value,
  sub,
  tone = "default",
  Icon,
}: {
  label: string;
  value: string;
  sub: string;
  tone?: "default" | "up" | "down";
  Icon: typeof Coins;
}) {
  const toneClass = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-foreground";
  return (
    <div className="panel px-4 py-3">
      <div className="label-caps flex items-center gap-2">
        <Icon className="size-3 opacity-50" aria-hidden />
        {label}
      </div>
      <div className={`tape mt-2 text-xl font-semibold ${toneClass}`}>{value}</div>
      <div className="tape mt-1 text-[10px] text-muted-foreground">{sub}</div>
    </div>
  );
}

/** Real worker portfolio figures plus the conviction the desk is trading on. */
export function WorkerMetricsPanel() {
  const fetchConviction = useServerFn(getDeskConviction);

  const portfolio = useQuery({
    queryKey: ["bot-status", "worker-metrics"],
    queryFn: async (): Promise<WorkerPortfolio> => {
      const res = await fetch("/api/public/worker-metrics", { cache: "no-store" });
      if (!res.ok) throw new Error(`worker metrics unavailable (${res.status})`);
      return (await res.json()) as WorkerPortfolio;
    },
    refetchInterval: 15_000,
    retry: 1,
  });

  const conviction = useQuery({
    queryKey: ["bot-status", "desk-conviction"],
    queryFn: () => fetchConviction(),
    refetchInterval: 30_000,
    retry: false,
  });

  if (portfolio.isError) {
    return (
      <div className="panel border-down/40 bg-down/10 px-4 py-3">
        <p className="label-caps text-down">worker balance & equity unavailable</p>
        <p className="tape mt-1 text-[10px] text-muted-foreground">
          {portfolio.error instanceof Error ? portfolio.error.message : "worker unreachable"}
        </p>
      </div>
    );
  }

  const data = portfolio.data;
  const c = conviction.data;
  const avgPct = c?.avgConviction != null ? `${(c.avgConviction * 100).toFixed(0)}%` : "—";

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Tile
        label="Worker balance"
        value={data ? money(data.balance) : "—"}
        sub={data ? `bankroll ${money(data.bankroll)} · ${data.mode} mode` : "loading worker…"}
        Icon={Coins}
      />
      <Tile
        label="Worker equity"
        value={data ? money(data.equity) : "—"}
        sub={data ? `realized ${money(data.realizedPnl)} · today ${money(data.dailyPnl)}` : "loading worker…"}
        tone={data ? (data.equity >= data.bankroll ? "up" : "down") : "default"}
        Icon={LineChart}
      />
      <Tile
        label="Open positions"
        value={data ? String(data.openPositions) : "—"}
        sub={data ? `${money(data.openExposure)} exposure at entry` : "loading worker…"}
        Icon={Layers}
      />
      <Tile
        label="Desk conviction"
        value={avgPct}
        sub={
          c
            ? `${c.samples} orders · ${c.mirrored} accepted · ${c.rejected} no-edge`
            : "sign in to the desk to track conviction"
        }
        Icon={Gauge}
      />
    </div>
  );
}

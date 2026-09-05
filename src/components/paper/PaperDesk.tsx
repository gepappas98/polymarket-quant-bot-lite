import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { toast } from "sonner";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, RotateCcw, ShieldCheck } from "lucide-react";

import { getBotStatus } from "@/lib/bot.functions";
import {
  checkPaperGates,
  getPaperState,
  paperBuy,
  paperSell,
  resetPaperAccount,
} from "@/lib/paper.functions";

const money = (n: number) => `${n < 0 ? "-" : ""}$${Math.abs(n).toFixed(2)}`;
const pnlClass = (n: number) => (n > 0 ? "text-up" : n < 0 ? "text-down" : "text-muted-foreground");

type PaperMarket = {
  slug: string;
  upAsk: number;
  downAsk: number;
  upBid: number;
  downBid: number;
};

type PaperPosition = {
  id: string;
  market: string;
  side: "UP" | "DOWN";
  shares: number;
  avgPrice: number;
  costUsd: number;
};

type PaperGate = { name: string; allowed: boolean; reason: string };

type PaperTrade = {
  id: string;
  createdAt: string;
  market: string;
  side: string;
  action: "BUY" | "SELL";
  price: number;
  sizeUsd: number;
  realizedPnl: number;
  cashAfter: number;
};

export function PaperDesk() {
  const fetchState = useServerFn(getPaperState);
  const fetchStatus = useServerFn(getBotStatus);
  const runGates = useServerFn(checkPaperGates);
  const buy = useServerFn(paperBuy);
  const sell = useServerFn(paperSell);
  const reset = useServerFn(resetPaperAccount);
  const qc = useQueryClient();

  const state = useQuery({
    queryKey: ["paper-state"],
    queryFn: () => fetchState(),
    refetchInterval: 10_000,
  });
  const status = useQuery({
    queryKey: ["bot-status"],
    queryFn: () => fetchStatus(),
    refetchInterval: 5_000,
  });

  const markets = (status.data?.markets ?? []) as PaperMarket[];
  const [market, setMarket] = useState<string>("");
  const [side, setSide] = useState<"UP" | "DOWN">("UP");
  const [sizeUsd, setSizeUsd] = useState(100);

  const selected = useMemo(
    () => markets.find((m) => m.slug === market) ?? markets[0],
    [markets, market],
  );
  const askPrice = selected ? (side === "UP" ? selected.upAsk : selected.downAsk) : 0;

  const quoteFor = (slug: string, positionSide: "UP" | "DOWN") => {
    const row = markets.find((m) => m.slug === slug);
    if (!row) return null;
    return positionSide === "UP" ? row.upBid : row.downBid;
  };

  const gates = useQuery({
    queryKey: ["paper-gates", selected?.slug, sizeUsd],
    queryFn: () => runGates({ data: { market: selected!.slug, sizeUsd } }),
    enabled: Boolean(selected) && sizeUsd > 0,
    refetchInterval: 10_000,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["paper-state"] });
    qc.invalidateQueries({ queryKey: ["paper-gates"] });
  };

  const buyMutation = useMutation({
    mutationFn: () =>
      buy({ data: { market: selected!.slug, side, price: askPrice, sizeUsd, reason: "manual paper buy" } }),
    onSuccess: (result) => {
      if (result.status === "blocked") {
        toast.error(`Blocked: ${result.gates.filter((g) => !g.allowed).map((g) => g.name).join(", ")}`);
      } else {
        toast.success(`Paper filled ${sizeUsd.toFixed(2)} USD @ ${askPrice.toFixed(3)}`);
      }
      invalidate();
    },
    onError: () => toast.error("Paper buy failed"),
  });

  const sellMutation = useMutation({
    mutationFn: (vars: { positionId: string; price: number }) =>
      sell({ data: { positionId: vars.positionId, price: vars.price, fraction: 1 } }),
    onSuccess: (result) => {
      if (result.status === "closed") {
        toast.success(`Closed — realized ${money(result.realized)}`);
      }
      invalidate();
    },
    onError: () => toast.error("Paper close failed"),
  });

  const resetMutation = useMutation({
    mutationFn: () => reset({ data: { startingBankroll: 10_000 } }),
    onSuccess: () => {
      toast.success("Paper account reset to $10,000");
      invalidate();
    },
  });

  const account = state.data?.account;
  const positions = state.data?.positions ?? [];

  const unrealized = (positions as PaperPosition[]).reduce((sum: number, p: PaperPosition) => {
    const bid = quoteFor(p.market, p.side);
    if (bid == null) return sum;
    return sum + (p.shares * bid - p.costUsd);
  }, 0);
  const openCost = (positions as PaperPosition[]).reduce((sum: number, p: PaperPosition) => sum + p.costUsd, 0);
  const equity = (account?.cash ?? 0) + openCost + unrealized;
  const dailyUsedPct = account
    ? Math.min(100, Math.max(0, (-Math.min(0, account.dailyPnl) / account.dailyLossLimit) * 100))
    : 0;

  return (
    <div className="relative">
      {/* PAPER watermark — impossible to mistake for live trading */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center overflow-hidden"
      >
        <span className="rotate-[-18deg] select-none text-[16vw] font-black leading-none tracking-tighter text-primary/[0.06]">
          PAPER
        </span>
      </div>

      <div className="relative z-20 space-y-3">
        <div className="panel flex flex-wrap items-center gap-x-4 gap-y-2 border-warning/40 bg-warning/10 px-3 py-2">
          <span className="tape flex items-center gap-2 rounded border border-warning/60 px-2 py-1 text-[10px] uppercase text-warning">
            <AlertTriangle className="size-3" /> paper engine — simulated money only
          </span>
          <span className="tape text-[10px] uppercase text-muted-foreground">
            engine {state.isError ? "offline" : state.data ? "active" : "connecting"} · quotes{" "}
            {status.data?.source === "worker" ? "worker feed" : "demo feed"}
          </span>
          <button
            onClick={() => resetMutation.mutate()}
            disabled={resetMutation.isPending}
            className="tape ml-auto flex items-center gap-1 rounded border border-border px-2 py-1 text-[10px] uppercase text-muted-foreground hover:text-foreground"
          >
            <RotateCcw className="size-3" /> reset paper account
          </button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="bankroll (equity)" value={money(equity)} sub={`cash ${money(account?.cash ?? 0)}`} />
          <Stat
            label="unrealized p&l"
            value={money(unrealized)}
            valueClass={pnlClass(unrealized)}
            sub={`${positions.length} open position${positions.length === 1 ? "" : "s"}`}
          />
          <Stat
            label="realized p&l"
            value={money(account?.realizedPnl ?? 0)}
            valueClass={pnlClass(account?.realizedPnl ?? 0)}
            sub={`today ${money(account?.dailyPnl ?? 0)}`}
          />
          <div className="panel px-3 py-3">
            <p className="label-caps text-[10px] text-muted-foreground">daily loss limit</p>
            <p className="tape mt-1 text-lg">{money(account?.dailyLossLimit ?? 0)}</p>
            <div className="mt-2 h-1.5 w-full rounded bg-muted">
              <div className="h-1.5 rounded bg-down" style={{ width: `${dailyUsedPct}%` }} />
            </div>
            <p className="tape mt-1 text-[10px] text-muted-foreground">
              {dailyUsedPct.toFixed(0)}% used
            </p>
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-3">
          <div className="panel space-y-3 px-3 py-3 lg:col-span-1">
            <h2 className="label-caps text-[11px]">place paper order</h2>
            <label className="block">
              <span className="tape text-[10px] uppercase text-muted-foreground">market</span>
              <select
                value={selected?.slug ?? ""}
                onChange={(e) => setMarket(e.target.value)}
                className="tape mt-1 w-full rounded border border-border bg-muted px-2 py-1 text-xs"
              >
                {markets.map((m) => (
                  <option key={m.slug} value={m.slug}>
                    {m.slug}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex gap-2">
              {(["UP", "DOWN"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setSide(s)}
                  className={`tape flex-1 rounded border px-2 py-1 text-[10px] uppercase ${
                    side === s
                      ? s === "UP"
                        ? "border-up/60 bg-up/15 text-up"
                        : "border-down/60 bg-down/15 text-down"
                      : "border-border text-muted-foreground"
                  }`}
                >
                  {s === "UP" ? <ArrowUpRight className="mr-1 inline size-3" /> : <ArrowDownRight className="mr-1 inline size-3" />}
                  {s}
                </button>
              ))}
            </div>
            <label className="block">
              <span className="tape text-[10px] uppercase text-muted-foreground">size (usd)</span>
              <input
                type="number"
                min={1}
                step={1}
                value={sizeUsd}
                onChange={(e) => setSizeUsd(Number(e.target.value))}
                className="tape mt-1 w-full rounded border border-border bg-muted px-2 py-1 text-xs"
              />
            </label>
            <p className="tape text-[11px] text-muted-foreground">
              ask {askPrice.toFixed(3)} · {askPrice > 0 ? (sizeUsd / askPrice).toFixed(1) : "0"} shares
            </p>

            <div className="space-y-1 rounded border border-border bg-muted/40 p-2">
              <p className="label-caps flex items-center gap-1 text-[10px]">
                <ShieldCheck className="size-3" /> risk gates
              </p>
              {(gates.data?.gates ?? []).map((g: PaperGate) => (
                <p key={g.name} className="tape flex items-baseline gap-2 text-[10px]">
                  <span className={g.allowed ? "text-up" : "text-down"}>{g.allowed ? "PASS" : "BLOCK"}</span>
                  <span className="text-foreground">{g.name}</span>
                  <span className="truncate text-muted-foreground">{g.reason}</span>
                </p>
              ))}
              {!gates.data ? <p className="tape text-[10px] text-muted-foreground">evaluating…</p> : null}
            </div>

            <button
              onClick={() => buyMutation.mutate()}
              disabled={!selected || askPrice <= 0 || sizeUsd <= 0 || buyMutation.isPending || gates.data?.allowed === false}
              className="tape w-full rounded border border-primary/60 bg-primary/20 px-2 py-2 text-[11px] uppercase text-primary disabled:opacity-40"
            >
              {buyMutation.isPending ? "submitting…" : "paper buy"}
            </button>
          </div>

          <div className="panel px-3 py-3 lg:col-span-2">
            <h2 className="label-caps mb-2 text-[11px]">open paper positions</h2>
            {positions.length === 0 ? (
              <p className="tape text-[11px] text-muted-foreground">no open positions</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[11px]">
                  <thead className="label-caps text-[10px] text-muted-foreground">
                    <tr>
                      <th className="py-1">market</th>
                      <th>side</th>
                      <th className="text-right">shares</th>
                      <th className="text-right">avg</th>
                      <th className="text-right">bid</th>
                      <th className="text-right">unreal.</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody className="tape">
                    {(positions as PaperPosition[]).map((p: PaperPosition) => {
                      const bid = quoteFor(p.market, p.side);
                      const upnl = bid == null ? 0 : p.shares * bid - p.costUsd;
                      return (
                        <tr key={p.id} className="border-t border-border/60">
                          <td className="max-w-[180px] truncate py-1">{p.market}</td>
                          <td className={p.side === "UP" ? "text-up" : "text-down"}>{p.side}</td>
                          <td className="text-right">{p.shares.toFixed(1)}</td>
                          <td className="text-right">{p.avgPrice.toFixed(3)}</td>
                          <td className="text-right">{bid == null ? "—" : bid.toFixed(3)}</td>
                          <td className={`text-right ${pnlClass(upnl)}`}>{money(upnl)}</td>
                          <td className="text-right">
                            <button
                              disabled={bid == null || sellMutation.isPending}
                              onClick={() => sellMutation.mutate({ positionId: p.id, price: bid ?? 0.5 })}
                              className="tape rounded border border-border px-2 py-0.5 text-[10px] uppercase hover:border-down/60 hover:text-down disabled:opacity-40"
                            >
                              close
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <div className="panel px-3 py-3">
          <h2 className="label-caps mb-2 text-[11px]">paper ledger / trade history</h2>
          {(state.data?.trades ?? []).length === 0 ? (
            <p className="tape text-[11px] text-muted-foreground">no paper trades yet</p>
          ) : (
            <div className="max-h-80 overflow-auto">
              <table className="w-full text-left text-[11px]">
                <thead className="label-caps sticky top-0 bg-card text-[10px] text-muted-foreground">
                  <tr>
                    <th className="py-1">time (utc)</th>
                    <th>market</th>
                    <th>action</th>
                    <th className="text-right">price</th>
                    <th className="text-right">size</th>
                    <th className="text-right">realized</th>
                    <th className="text-right">cash after</th>
                  </tr>
                </thead>
                <tbody className="tape">
                  {(state.data?.trades ?? []).map((t: PaperTrade) => (
                    <tr key={t.id} className="border-t border-border/60">
                      <td className="py-1 text-muted-foreground">
                        {new Date(t.createdAt).toISOString().slice(5, 19).replace("T", " ")}
                      </td>
                      <td className="max-w-[180px] truncate">{t.market}</td>
                      <td className={t.action === "BUY" ? "text-up" : "text-down"}>
                        {t.action} {t.side}
                      </td>
                      <td className="text-right">{t.price.toFixed(3)}</td>
                      <td className="text-right">{money(t.sizeUsd)}</td>
                      <td className={`text-right ${pnlClass(t.realizedPnl)}`}>
                        {t.realizedPnl === 0 ? "—" : money(t.realizedPnl)}
                      </td>
                      <td className="text-right text-muted-foreground">{money(t.cashAfter)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  valueClass = "",
}: {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <div className="panel px-3 py-3">
      <p className="label-caps text-[10px] text-muted-foreground">{label}</p>
      <p className={`tape mt-1 text-lg ${valueClass}`}>{value}</p>
      {sub ? <p className="tape mt-1 text-[10px] text-muted-foreground">{sub}</p> : null}
    </div>
  );
}

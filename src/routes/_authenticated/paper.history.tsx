import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { useState } from "react";
import { getPaperHistory } from "@/lib/paper.functions";

export const Route = createFileRoute("/_authenticated/paper/history")({
  component: PaperHistoryPage,
});

const money = (n: number) => `${n < 0 ? "-" : ""}$${Math.abs(n).toFixed(2)}`;

function PaperHistoryPage() {
  const fetchHistory = useServerFn(getPaperHistory);
  const [action, setAction] = useState<"" | "BUY" | "SELL">("");
  const [market, setMarket] = useState("");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["paper-history", action, market],
    queryFn: () =>
      fetchHistory({
        data: {
          limit: 200,
          ...(action ? { action } : {}),
          ...(market.trim() ? { market: market.trim() } : {}),
        },
      }),
    refetchInterval: 20_000,
  });

  return (
    <section className="panel px-4 py-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="label-caps text-[11px]">paper trade history</h2>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <input
            value={market}
            onChange={(e) => setMarket(e.target.value)}
            placeholder="filter market"
            className="tape rounded border border-border bg-background px-2 py-1 text-[11px]"
          />
          <select
            value={action}
            onChange={(e) => setAction(e.target.value as "" | "BUY" | "SELL")}
            className="tape rounded border border-border bg-background px-2 py-1 text-[11px]"
          >
            <option value="">all</option>
            <option value="BUY">buy</option>
            <option value="SELL">sell</option>
          </select>
        </div>
      </div>

      {isLoading ? <p className="label-caps">Loading…</p> : null}
      {isError ? (
        <p className="text-sm text-down">{(error as Error).message}</p>
      ) : null}

      {data ? (
        <>
          <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="trades" value={String(data.stats.count)} />
            <Stat label="closed" value={String(data.stats.closed)} />
            <Stat label="win rate" value={`${(data.stats.winRate * 100).toFixed(1)}%`} />
            <Stat label="realized" value={money(data.stats.realizedPnl)} />
          </div>

          {data.trades.length === 0 ? (
            <p className="tape text-[11px] text-muted-foreground">No trades match this filter.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="tape text-[10px] uppercase text-muted-foreground">
                  <tr>
                    <th className="py-1 pr-3">time</th>
                    <th className="py-1 pr-3">market</th>
                    <th className="py-1 pr-3">side</th>
                    <th className="py-1 pr-3">action</th>
                    <th className="py-1 pr-3 text-right">price</th>
                    <th className="py-1 pr-3 text-right">shares</th>
                    <th className="py-1 pr-3 text-right">size</th>
                    <th className="py-1 pr-3 text-right">realized</th>
                    <th className="py-1 text-right">cash after</th>
                  </tr>
                </thead>
                <tbody>
                  {data.trades.map((t) => (
                    <tr key={t.id} className="border-t border-border/60">
                      <td className="py-1 pr-3 tabular-nums">{new Date(t.createdAt).toLocaleString()}</td>
                      <td className="py-1 pr-3">{t.market}</td>
                      <td className="py-1 pr-3">{t.side}</td>
                      <td className="py-1 pr-3">{t.action}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">{t.price.toFixed(3)}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">{t.shares.toFixed(2)}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">{money(t.sizeUsd)}</td>
                      <td
                        className={`py-1 pr-3 text-right tabular-nums ${t.realizedPnl > 0 ? "text-up" : t.realizedPnl < 0 ? "text-down" : ""}`}
                      >
                        {money(t.realizedPnl)}
                      </td>
                      <td className="py-1 text-right tabular-nums">{money(t.cashAfter)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-border px-2 py-1">
      <p className="tape text-[10px] uppercase text-muted-foreground">{label}</p>
      <p className="text-sm font-semibold tabular-nums">{value}</p>
    </div>
  );
}

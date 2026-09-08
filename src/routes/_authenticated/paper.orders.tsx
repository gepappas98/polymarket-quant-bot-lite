import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { useState } from "react";
import { listPaperOrders } from "@/lib/paper.functions";

export const Route = createFileRoute("/_authenticated/paper/orders")({
  component: PaperOrdersPage,
});

function PaperOrdersPage() {
  const fetchOrders = useServerFn(listPaperOrders);
  const [expanded, setExpanded] = useState<string | null>(null);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["paper-orders"],
    queryFn: () => fetchOrders({ data: { limit: 100 } }),
    refetchInterval: 15_000,
  });

  if (isLoading) return <p className="label-caps">Loading orders…</p>;
  if (isError)
    return (
      <div className="panel border-down/50 bg-down/10 px-4 py-3 text-sm text-down">
        {(error as Error).message}
      </div>
    );

  const orders = data ?? [];

  return (
    <section className="panel px-4 py-4">
      <h2 className="label-caps mb-3 text-[11px]">paper order blotter</h2>
      {orders.length === 0 ? (
        <p className="tape text-[11px] text-muted-foreground">No paper orders yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="tape text-[10px] uppercase text-muted-foreground">
              <tr>
                <th className="py-1 pr-3">time</th>
                <th className="py-1 pr-3">market</th>
                <th className="py-1 pr-3">side</th>
                <th className="py-1 pr-3">action</th>
                <th className="py-1 pr-3">state</th>
                <th className="py-1 pr-3 text-right">req</th>
                <th className="py-1 pr-3 text-right">filled</th>
                <th className="py-1 pr-3 text-right">vwap</th>
                <th className="py-1 pr-3 text-right">fees</th>
                <th className="py-1 text-right">fills</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <>
                  <tr
                    key={o.id}
                    className="cursor-pointer border-t border-border/60 hover:bg-muted/40"
                    onClick={() => setExpanded(expanded === o.id ? null : o.id)}
                  >
                    <td className="py-1 pr-3 tabular-nums">
                      {new Date(o.createdAt).toLocaleTimeString()}
                    </td>
                    <td className="py-1 pr-3">{o.market}</td>
                    <td className="py-1 pr-3">{o.side}</td>
                    <td className="py-1 pr-3">{o.action}</td>
                    <td className="py-1 pr-3">{o.state}</td>
                    <td className="py-1 pr-3 text-right tabular-nums">{o.requestedShares.toFixed(2)}</td>
                    <td className="py-1 pr-3 text-right tabular-nums">{o.filledShares.toFixed(2)}</td>
                    <td className="py-1 pr-3 text-right tabular-nums">{o.avgFillPrice.toFixed(3)}</td>
                    <td className="py-1 pr-3 text-right tabular-nums">{o.fees.toFixed(2)}</td>
                    <td className="py-1 text-right tabular-nums">{o.fills.length}</td>
                  </tr>
                  {expanded === o.id
                    ? o.fills.map((f) => (
                        <tr key={f.id} className="bg-muted/30 text-[11px] text-muted-foreground">
                          <td className="py-1 pr-3" colSpan={4}>
                            fill · {new Date(f.filledAt).toLocaleString()}
                          </td>
                          <td className="py-1 pr-3" colSpan={2}>
                            {f.shares.toFixed(2)} shares
                          </td>
                          <td className="py-1 pr-3 text-right tabular-nums" colSpan={2}>
                            @ {f.price.toFixed(3)}
                          </td>
                          <td className="py-1 text-right tabular-nums" colSpan={2}>
                            fee {f.fee.toFixed(2)}
                          </td>
                        </tr>
                      ))
                    : null}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

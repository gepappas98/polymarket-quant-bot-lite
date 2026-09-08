import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { toast } from "sonner";
import { reconcilePaperAccount } from "@/lib/paper.functions";

export const Route = createFileRoute("/_authenticated/paper/reconcile")({
  component: PaperReconcilePage,
});

const money = (n: number) => `${n < 0 ? "-" : ""}$${Math.abs(n).toFixed(2)}`;

function PaperReconcilePage() {
  const check = useServerFn(reconcilePaperAccount);
  const queryClient = useQueryClient();

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["paper-reconcile"],
    queryFn: () => check({ data: { apply: false } }),
  });

  const apply = useMutation({
    mutationFn: () => check({ data: { apply: true } }),
    onSuccess: (result) => {
      toast.success(result.applied ? "Account rebalanced from the ledger" : "Nothing to repair");
      queryClient.invalidateQueries({ queryKey: ["paper-reconcile"] });
      queryClient.invalidateQueries({ queryKey: ["paper-state"] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  if (isLoading) return <p className="label-caps">Reconciling…</p>;
  if (isError)
    return <div className="panel border-down/50 bg-down/10 px-4 py-3 text-sm text-down">{(error as Error).message}</div>;
  if (!data) return null;

  return (
    <div className="space-y-3">
      <section className="panel px-4 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="label-caps text-[11px]">ledger reconciliation</h2>
          <span
            className={`tape rounded border px-2 py-1 text-[10px] uppercase ${
              data.inSync ? "border-up/50 bg-up/10 text-up" : "border-warning/50 bg-warning/10 text-warning"
            }`}
          >
            {data.inSync ? "in sync" : "drift detected"}
          </span>
          <div className="ml-auto flex gap-2">
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="tape rounded border border-border px-2 py-1 text-[10px] uppercase text-muted-foreground hover:text-foreground"
            >
              re-check
            </button>
            <button
              onClick={() => apply.mutate()}
              disabled={apply.isPending || data.inSync}
              className="tape rounded border border-primary/50 bg-primary/15 px-2 py-1 text-[10px] uppercase text-primary disabled:opacity-40"
            >
              repair account
            </button>
          </div>
        </div>
        <p className="tape mt-2 text-[11px] text-muted-foreground">
          checked {new Date(data.checkedAt).toLocaleString()} · {data.ledger.trades} trades ·{" "}
          {data.ledger.orders} orders · {data.ledger.positions} positions
        </p>
      </section>

      <section className="panel px-4 py-4">
        <h3 className="label-caps mb-2 text-[11px]">stored vs recomputed</h3>
        <table className="w-full text-left text-xs">
          <thead className="tape text-[10px] uppercase text-muted-foreground">
            <tr>
              <th className="py-1 pr-3">field</th>
              <th className="py-1 pr-3 text-right">stored</th>
              <th className="py-1 pr-3 text-right">from ledger</th>
              <th className="py-1 text-right">drift</th>
            </tr>
          </thead>
          <tbody>
            <Row label="cash" stored={data.account.cash} computed={data.computed.cash} drift={data.drift.cash} />
            <Row
              label="realized P&L"
              stored={data.account.realizedPnl}
              computed={data.computed.realizedPnl}
              drift={data.drift.realizedPnl}
            />
            <tr className="border-t border-border/60">
              <td className="py-1 pr-3">open position cost</td>
              <td className="py-1 pr-3 text-right tabular-nums">—</td>
              <td className="py-1 pr-3 text-right tabular-nums">{money(data.computed.positionCost)}</td>
              <td className="py-1 text-right tabular-nums">—</td>
            </tr>
            <tr className="border-t border-border/60">
              <td className="py-1 pr-3">equity</td>
              <td className="py-1 pr-3 text-right tabular-nums">—</td>
              <td className="py-1 pr-3 text-right tabular-nums">{money(data.computed.equity)}</td>
              <td className="py-1 text-right tabular-nums">—</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section className="panel px-4 py-4">
        <h3 className="label-caps mb-2 text-[11px]">orders without a ledger trade</h3>
        {data.orphanOrders.length === 0 ? (
          <p className="tape text-[11px] text-muted-foreground">None — every order has a matching trade.</p>
        ) : (
          <ul className="space-y-1 text-xs">
            {data.orphanOrders.map((o) => (
              <li key={o.id} className="flex flex-wrap gap-2 border-t border-border/60 py-1">
                <span>{o.market}</span>
                <span className="text-muted-foreground">{o.state}</span>
                <span className="tape ml-auto text-[10px] text-muted-foreground">
                  {new Date(o.createdAt).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Row({
  label,
  stored,
  computed,
  drift,
}: {
  label: string;
  stored: number;
  computed: number;
  drift: number;
}) {
  return (
    <tr className="border-t border-border/60">
      <td className="py-1 pr-3">{label}</td>
      <td className="py-1 pr-3 text-right tabular-nums">{money(stored)}</td>
      <td className="py-1 pr-3 text-right tabular-nums">{money(computed)}</td>
      <td className={`py-1 text-right tabular-nums ${Math.abs(drift) > 0.005 ? "text-warning" : ""}`}>
        {money(drift)}
      </td>
    </tr>
  );
}

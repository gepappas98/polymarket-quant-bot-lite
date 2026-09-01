import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/dashboard/Panels";
import { NavLinks } from "@/components/dashboard/NavLinks";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getLeaders, refreshLeaders, riskQueryKeys, type Leader } from "@/lib/riskApi";

export const Route = createFileRoute("/leaders")({
  head: () => ({
    meta: [
      { title: "Leaders — Polymarket Quant Bot" },
      {
        name: "description",
        content: "Risk-adjusted performance leaderboard for Polymarket traders.",
      },
    ],
  }),
  component: LeadersPage,
});

function LeadersPage() {
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const leaders = useQuery({
    queryKey: riskQueryKeys.leaders(),
    queryFn: () => getLeaders(),
  });

  async function refresh() {
    setRefreshing(true);
    setRefreshError(null);
    try {
      await refreshLeaders(true);
      await queryClient.invalidateQueries({ queryKey: riskQueryKeys.leaders() });
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : "Unable to refresh leaderboard");
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-10">
      <header className="panel mb-6 flex flex-wrap items-center gap-4 px-4 py-4">
        <div>
          <h1 className="text-lg font-bold tracking-tight sm:text-xl">Risk leaderboard</h1>
          <p className="tape mt-1 text-[11px] text-muted-foreground">
            composite performance across the trader cohort
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <NavLinks />
          <Button size="sm" onClick={() => void refresh()} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      </header>

      {leaders.isError || refreshError ? <OfflineNotice /> : null}
      <Panel
        title="Trader rankings"
        hint={leaders.data ? `${leaders.data.length} traders` : "loading"}
      >
        {leaders.isLoading ? (
          <p className="px-4 py-8 text-center tape text-muted-foreground">Loading leaderboard…</p>
        ) : leaders.data?.length ? (
          <LeaderTable leaders={leaders.data} />
        ) : (
          <p className="px-4 py-8 text-center tape text-muted-foreground">
            No leaderboard data yet.
          </p>
        )}
      </Panel>
    </main>
  );
}

function LeaderTable({ leaders }: { leaders: Leader[] }) {
  return (
    <Table className="min-w-[760px]">
      <TableHeader>
        <TableRow className="label-caps">
          <TableHead className="font-normal">Address</TableHead>
          <TableHead className="text-right font-normal">Composite</TableHead>
          <TableHead className="text-right font-normal">Sharpe</TableHead>
          <TableHead className="text-right font-normal">Win-rate</TableHead>
          <TableHead className="text-right font-normal">ROI</TableHead>
          <TableHead className="text-right font-normal">Drawdown</TableHead>
          <TableHead className="text-right font-normal">Trades</TableHead>
          <TableHead className="text-right font-normal">Last updated</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {leaders.map((leader) => (
          <TableRow key={leader.address} className="border-border/60">
            <TableCell className="font-medium" title={leader.address}>
              {truncateAddress(leader.address)}
            </TableCell>
            <TableCell className="tape text-right text-primary">
              {leader.composite_score.toFixed(2)}
            </TableCell>
            <TableCell className="tape text-right">{leader.sharpe_ratio.toFixed(2)}</TableCell>
            <TableCell className="tape text-right">{leader.win_rate.toFixed(1)}%</TableCell>
            <TableCell className="tape text-right">{leader.roi.toFixed(1)}%</TableCell>
            <TableCell className="tape text-right">{leader.max_drawdown.toFixed(1)}%</TableCell>
            <TableCell className="tape text-right">{leader.trade_count}</TableCell>
            <TableCell className="tape text-right text-muted-foreground">
              {leader.last_updated ? new Date(leader.last_updated).toLocaleString() : "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function truncateAddress(address: string) {
  return address.length > 12 ? `${address.slice(0, 6)}…${address.slice(-4)}` : address;
}

function OfflineNotice() {
  return (
    <div className="mb-3 rounded-md border border-warn/40 bg-warn/10 px-4 py-3 tape text-[11px] text-warn">
      API offline — start <code>uvicorn app.main:app</code>
    </div>
  );
}

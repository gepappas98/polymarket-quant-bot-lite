import { useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { toast } from "sonner";
import { Panel } from "@/components/dashboard/Panels";
import { Badge } from "@/components/ui/badge";
import type { ObservedTraderActivity } from "@/lib/copyActivity";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { supabase } from "@/integrations/supabase/client";
import { fetchWalletActivity } from "@/lib/copy.functions";
import { decideCopy } from "@/lib/copyActivity";

export const IS_SIMULATION_ONLY = false;

export function CopyTradingPanel() {
  const qc = useQueryClient();
  const activityFn = useServerFn(fetchWalletActivity);
  const [wallet, setWallet] = useState("");
  const [label, setLabel] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const { data: watchlist } = useQuery({
    queryKey: ["copy-watchlist"],
    queryFn: async () => {
      const { data, error } = await supabase.from("copy_watchlist").select("id, wallet_address, label, active").order("created_at", { ascending: false });
      if (error) throw error;
      return data;
    },
  });
  const selectedWallet = watchlist?.find((row) => row.wallet_address === selected);
  const activity = useQuery({
    queryKey: ["copy-activity", selected],
    queryFn: () => activityFn({ data: { wallet: selected!, limit: 50 } }),
    enabled: Boolean(selected && selectedWallet?.active),
    refetchInterval: 15_000,
  });
  const addWallet = useMutation({
    mutationFn: async () => {
      const { data: auth } = await supabase.auth.getUser();
      if (!auth.user) throw new Error("Sign in to watch a wallet");
      const { error } = await supabase.from("copy_watchlist").insert({ user_id: auth.user.id, wallet_address: wallet.trim(), label: label.trim() || "unnamed" });
      if (error) throw error;
    },
    onSuccess: () => {
      setWallet(""); setLabel(""); toast.success("Wallet added to watchlist"); void qc.invalidateQueries({ queryKey: ["copy-watchlist"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <Panel title="Copy trading" hint="verified Polymarket activity" className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 px-4 pt-4">
        <Badge variant="outline">OBSERVED_TRADE</Badge>
        <Badge variant="outline">PAPER only</Badge>
        <span className="tape text-[10px] uppercase text-warning">LIVE COPY DISABLED</span>
      </div>
      <p className="tape px-4 pt-2 text-[10px] text-muted-foreground">
        Activity comes from the Polymarket Data API. No positions are converted into trades and no browser-generated copy fills are written.
      </p>
      <div className="grid gap-3 px-4 py-4 sm:grid-cols-[2fr_1fr_auto]">
        <div className="space-y-1.5"><Label className="label-caps" htmlFor="ct-wallet">Wallet address</Label><Input id="ct-wallet" placeholder="0x…" value={wallet} onChange={(event) => setWallet(event.target.value)} /></div>
        <div className="space-y-1.5"><Label className="label-caps" htmlFor="ct-label">Label</Label><Input id="ct-label" value={label} onChange={(event) => setLabel(event.target.value)} /></div>
        <div className="flex items-end"><Button onClick={() => addWallet.mutate()} disabled={!/^0x[a-fA-F0-9]{40}$/.test(wallet.trim())}>Watch</Button></div>
      </div>
      <ul className="divide-y divide-border/60 border-y border-border">
        {(watchlist ?? []).length === 0 ? <li className="tape px-4 py-3 text-[11px] text-muted-foreground">Watchlist is empty.</li> : (watchlist ?? []).map((row) => (
          <li key={row.id} className="flex items-center gap-3 px-4 py-2.5">
            <span className={`size-2 rounded-full ${row.active ? "bg-up" : "bg-muted-foreground"}`} aria-hidden />
            <div className="min-w-0"><div className="text-sm font-medium">{row.label}</div><div className="tape truncate text-[10px] text-muted-foreground">{row.wallet_address}</div></div>
            <div className="ml-auto flex gap-2"><Button size="sm" variant="outline" onClick={() => setSelected(row.wallet_address)}>Activity</Button><Button size="sm" variant="ghost" onClick={async () => { await supabase.from("copy_watchlist").update({ active: !row.active }).eq("id", row.id); void qc.invalidateQueries({ queryKey: ["copy-watchlist"] }); }}>{row.active ? "Pause" : "Resume"}</Button></div>
          </li>
        ))}
      </ul>
      {selected ? <ActivityList state={activity} /> : null}
    </Panel>
  );
}

type ActivityState = { data: { activity?: ObservedTraderActivity[]; reason?: string } | undefined; isFetching: boolean };

function ActivityList({ state }: { state: ActivityState }) {
  const rows = state.data?.activity ?? [];
  return <div className="border-b border-border">
    <div className="flex items-center justify-between px-4 py-2"><span className="label-caps">Trader activity</span><span className="tape text-[10px] text-muted-foreground">{state.isFetching ? "refreshing…" : rows.length ? "REAL SOURCE" : `NO DATA${state.data?.reason ? ` — ${state.data.reason}` : ""}`}</span></div>
    {rows.length === 0 ? <p className="tape px-4 py-4 text-[11px] text-muted-foreground">NO DATA — no verified Polymarket activity is available.</p> : <ul className="divide-y divide-border/60 border-t border-border">{rows.map((event) => { const decision = decideCopy(event); return <li key={event.eventId} className="grid gap-1 px-4 py-3 text-[11px] sm:grid-cols-[1fr_auto_auto_auto] sm:items-center"><div><div className="font-medium">{event.market}</div><div className="tape text-muted-foreground">{event.tokenId} · {event.wallet.slice(0, 8)}…</div></div><span className={event.side === "BUY" ? "text-up" : "text-down"}>{event.side}</span><span>{event.quantity === null ? "quantity unavailable" : `${event.quantity} shares`}</span><Badge variant="outline">{decision.status === "ACCEPTED" ? "PAPER COPY" : decision.reason}</Badge><div className="tape text-muted-foreground">OBSERVED_TRADE · {new Date(event.timestamp).toLocaleString()}</div></li>; })}</ul>}
  </div>;
}

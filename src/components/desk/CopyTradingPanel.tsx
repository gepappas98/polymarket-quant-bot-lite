import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { toast } from "sonner";
import { Panel, usd } from "@/components/dashboard/Panels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { supabase } from "@/integrations/supabase/client";
import { fetchWalletPositions } from "@/lib/copy.functions";
import { logTrade } from "@/lib/trading.functions";

export function CopyTradingPanel() {
  const qc = useQueryClient();
  const positionsFn = useServerFn(fetchWalletPositions);
  const logFn = useServerFn(logTrade);
  const [wallet, setWallet] = useState("");
  const [label, setLabel] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const { data: watchlist } = useQuery({
    queryKey: ["copy-watchlist"],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("copy_watchlist")
        .select("id, wallet_address, label, active")
        .order("created_at", { ascending: false });
      if (error) throw error;
      return data;
    },
  });

  const { data: trades } = useQuery({
    queryKey: ["copy-trades"],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("copy_trades")
        .select("id, wallet, market, side, size, pnl, status, timestamp")
        .order("timestamp", { ascending: false })
        .limit(30);
      if (error) throw error;
      return data;
    },
  });

  const { data: positions, isFetching } = useQuery({
    queryKey: ["wallet-positions", selected],
    queryFn: () => positionsFn({ data: { wallet: selected! } }),
    enabled: !!selected,
  });

  const addWallet = useMutation({
    mutationFn: async () => {
      const { data: auth } = await supabase.auth.getUser();
      const { error } = await supabase.from("copy_watchlist").insert({
        user_id: auth.user!.id,
        wallet_address: wallet.trim(),
        label: label.trim() || "unnamed",
      });
      if (error) throw error;
    },
    onSuccess: () => {
      setWallet("");
      setLabel("");
      toast.success("Wallet added to watchlist");
      void qc.invalidateQueries({ queryKey: ["copy-watchlist"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const mirrored = new Map<string, number>();
  for (const t of trades ?? []) mirrored.set(t.market, (mirrored.get(t.market) ?? 0) + Number(t.size));

  const totalPnl = (trades ?? []).reduce((a, t) => a + Number(t.pnl), 0);

  return (
    <Panel title="Copy trading" hint="polymarket wallets" className="overflow-hidden">
      <div className="grid gap-3 px-4 py-4 sm:grid-cols-[2fr_1fr_auto]">
        <div className="space-y-1.5">
          <Label className="label-caps" htmlFor="ct-wallet">
            Wallet address
          </Label>
          <Input
            id="ct-wallet"
            placeholder="0x…"
            value={wallet}
            onChange={(e) => setWallet(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="label-caps" htmlFor="ct-label">
            Label
          </Label>
          <Input id="ct-label" value={label} onChange={(e) => setLabel(e.target.value)} />
        </div>
        <div className="flex items-end">
          <Button onClick={() => addWallet.mutate()} disabled={!/^0x[a-fA-F0-9]{40}$/.test(wallet.trim())}>
            Watch
          </Button>
        </div>
      </div>

      <ul className="divide-y divide-border/60 border-y border-border">
        {(watchlist ?? []).length === 0 ? (
          <li className="tape px-4 py-3 text-[11px] text-muted-foreground">Watchlist is empty.</li>
        ) : (
          (watchlist ?? []).map((w) => (
            <li key={w.id} className="flex items-center gap-3 px-4 py-2.5">
              <span
                className={`size-2 rounded-full ${w.active ? "bg-up" : "bg-muted-foreground"}`}
                aria-hidden
              />
              <div className="min-w-0">
                <div className="text-sm font-medium">{w.label}</div>
                <div className="tape truncate text-[10px] text-muted-foreground">
                  {w.wallet_address}
                </div>
              </div>
              <div className="ml-auto flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setSelected(w.wallet_address)}>
                  Positions
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={async () => {
                    await supabase
                      .from("copy_watchlist")
                      .update({ active: !w.active })
                      .eq("id", w.id);
                    void qc.invalidateQueries({ queryKey: ["copy-watchlist"] });
                  }}
                >
                  {w.active ? "Pause" : "Resume"}
                </Button>
              </div>
            </li>
          ))
        )}
      </ul>

      {selected ? (
        <div className="border-b border-border">
          <div className="label-caps px-4 py-2">
            Position diff · {isFetching ? "loading…" : positions?.ok ? "live" : (positions?.reason ?? "")}
          </div>
          <table className="w-full text-left">
            <thead>
              <tr className="label-caps border-y border-border">
                <th className="px-4 py-2 font-normal">Market</th>
                <th className="px-4 py-2 text-right font-normal">Their size</th>
                <th className="px-4 py-2 text-right font-normal">Mirrored</th>
                <th className="px-4 py-2 text-right font-normal">Their P&L</th>
                <th className="px-4 py-2 text-right font-normal" />
              </tr>
            </thead>
            <tbody>
              {(positions?.positions ?? []).map((p) => {
                const mine = mirrored.get(p.market) ?? 0;
                return (
                  <tr key={p.market + p.outcome} className="border-b border-border/60">
                    <td className="px-4 py-2 text-sm">
                      <div className="truncate">{p.market}</div>
                      <div className="tape text-[10px] text-muted-foreground">{p.outcome}</div>
                    </td>
                    <td className="tape px-4 py-2 text-right">{p.size.toFixed(2)}</td>
                    <td
                      className={`tape px-4 py-2 text-right ${mine < p.size ? "text-warn" : "text-up"}`}
                    >
                      {mine.toFixed(2)}
                    </td>
                    <td className={`tape px-4 py-2 text-right ${p.pnl >= 0 ? "text-up" : "text-down"}`}>
                      {usd(p.pnl)}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={async () => {
                          await logFn({
                            data: {
                              table: "copy_trades",
                              wallet: selected,
                              market: p.market,
                              side: p.outcome,
                              size: Math.max(p.size - mine, 1),
                              price: p.avgPrice,
                              status: "mirrored",
                            },
                          });
                          toast.success("Mirror logged");
                          void qc.invalidateQueries({ queryKey: ["copy-trades"] });
                        }}
                      >
                        Mirror
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="flex items-center justify-between px-4 py-3">
        <span className="label-caps">Copy performance</span>
        <span className={`tape text-sm ${totalPnl >= 0 ? "text-up" : "text-down"}`}>
          {usd(totalPnl)} · {trades?.length ?? 0} trades
        </span>
      </div>
    </Panel>
  );
}

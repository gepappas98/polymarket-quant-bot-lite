import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { format } from "date-fns";
import { toast } from "sonner";
import { Panel, usd } from "@/components/dashboard/Panels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { supabase } from "@/integrations/supabase/client";
import { getStrategy, strategies, type Candle, type SimResult } from "@/strategies/registry";

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];

async function loadCandles(symbol: string, start: string, end: string): Promise<Candle[]> {
  const url = new URL("https://api.binance.com/api/v3/klines");
  url.searchParams.set("symbol", symbol);
  url.searchParams.set("interval", "1h");
  url.searchParams.set("startTime", String(new Date(start).getTime()));
  url.searchParams.set("endTime", String(new Date(end).getTime()));
  url.searchParams.set("limit", "1000");
  const res = await fetch(url);
  if (!res.ok) throw new Error("Could not load candles from the price API");
  const rows = (await res.json()) as unknown[][];
  return rows.map((r) => ({
    time: Number(r[0]),
    open: Number(r[1]),
    high: Number(r[2]),
    low: Number(r[3]),
    close: Number(r[4]),
    volume: Number(r[5]),
  }));
}

export function BacktestConfig() {
  const qc = useQueryClient();
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [strategyId, setStrategyId] = useState(strategies[0]!.id);
  const [start, setStart] = useState(format(Date.now() - 20 * 86_400_000, "yyyy-MM-dd"));
  const [end, setEnd] = useState(format(Date.now(), "yyyy-MM-dd"));
  const [result, setResult] = useState<SimResult | null>(null);
  const [busy, setBusy] = useState(false);

  const { data: saved } = useQuery({
    queryKey: ["backtest-results"],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("backtest_results")
        .select("id, strategy, start_date, end_date, pnl, win_rate, trades")
        .order("created_at", { ascending: false })
        .limit(10);
      if (error) throw error;
      return data;
    },
  });

  async function run() {
    setBusy(true);
    try {
      const strategy = getStrategy(strategyId)!;
      const candles = await loadCandles(symbol, start, end);
      const sim = strategy.simulate(candles, strategy.defaults);
      setResult(sim);
      const { data: auth } = await supabase.auth.getUser();
      const { error } = await supabase.from("backtest_results").insert({
        user_id: auth.user!.id,
        strategy: strategyId,
        start_date: start,
        end_date: end,
        pnl: sim.pnl,
        win_rate: sim.winRate,
        trades: sim.trades.length,
        parameters: strategy.defaults,
        equity_curve: sim.equityCurve.slice(-500),
      });
      if (error) throw error;
      toast.success("Backtest saved");
      void qc.invalidateQueries({ queryKey: ["backtest-results"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Backtest failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Backtesting" hint="in-browser simulation" className="overflow-hidden">
      <div className="grid gap-3 px-4 py-4 sm:grid-cols-4">
        <div className="space-y-1.5">
          <Label className="label-caps">Symbol</Label>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
          >
            {SYMBOLS.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label className="label-caps">Strategy</Label>
          <select
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
            className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
          >
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label className="label-caps" htmlFor="bt-start">
            Start
          </Label>
          <Input id="bt-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label className="label-caps" htmlFor="bt-end">
            End
          </Label>
          <Input id="bt-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
      </div>

      <div className="px-4 pb-4">
        <Button onClick={run} disabled={busy} className="w-full sm:w-auto">
          {busy ? "Running…" : "Run backtest"}
        </Button>
      </div>

      {result ? (
        <>
          <div className="grid grid-cols-3 gap-px border-y border-border bg-border">
            {[
              ["P&L", usd(result.pnl)],
              ["Win rate", `${result.winRate}%`],
              ["Trades", String(result.trades.length)],
            ].map(([k, v]) => (
              <div key={k} className="bg-card px-4 py-3">
                <div className="label-caps">{k}</div>
                <div className="tape mt-1 text-sm">{v}</div>
              </div>
            ))}
          </div>
          <div className="h-40 px-2 py-3">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={result.equityCurve}>
                <YAxis hide domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }}
                  labelFormatter={(l) => new Date(Number(l)).toLocaleString()}
                />
                <Line type="monotone" dataKey="equity" dot={false} strokeWidth={1.5} stroke="currentColor" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : null}

      <ul className="divide-y divide-border/60 border-t border-border">
        {(saved ?? []).map((r) => (
          <li key={r.id} className="tape flex items-center gap-3 px-4 py-2 text-[11px]">
            <span>{r.strategy}</span>
            <span className="text-muted-foreground">
              {r.start_date} → {r.end_date}
            </span>
            <span className="text-muted-foreground">{r.trades} trades</span>
            <span className={`ml-auto ${Number(r.pnl) >= 0 ? "text-up" : "text-down"}`}>
              {usd(Number(r.pnl))} · {r.win_rate}%
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

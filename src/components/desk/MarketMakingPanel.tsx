import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { Panel, usd } from "@/components/dashboard/Panels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getMmStats } from "@/lib/trading.functions";
import { useMarketMaker } from "@/hooks/useMarketMaker";

const SYMBOLS = [
  { symbol: "btcusdt", label: "BTC" },
  { symbol: "ethusdt", label: "ETH" },
  { symbol: "solusdt", label: "SOL" },
];

export function MarketMakingPanel() {
  const [symbol, setSymbol] = useState("btcusdt");
  const [spreadBps, setSpreadBps] = useState(8);
  const [sizeUsd, setSizeUsd] = useState(25);
  const [running, setRunning] = useState(false);
  const market = `${symbol.replace("usdt", "").toUpperCase()}-MM`;

  const mm = useMarketMaker({ symbol, market, spreadBps, sizeUsd, running, cooldownSeconds: 120 });

  const statsFn = useServerFn(getMmStats);
  const { data: stats } = useQuery({
    queryKey: ["mm-stats", market, mm.fills.length],
    queryFn: () => statsFn({ data: { market, timeframeHours: 24 } }),
    refetchInterval: 30_000,
  });

  return (
    <Panel
      title="Market making"
      hint={mm.connected ? `${symbol} feed live` : "connecting feed…"}
      className="overflow-hidden"
    >
      <div className="grid gap-3 px-4 py-4 sm:grid-cols-4">
        <div className="space-y-1.5">
          <Label className="label-caps">Symbol</Label>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
          >
            {SYMBOLS.map((s) => (
              <option key={s.symbol} value={s.symbol}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label className="label-caps" htmlFor="mm-spread">
            Spread (bps)
          </Label>
          <Input
            id="mm-spread"
            type="number"
            value={spreadBps}
            min={1}
            onChange={(e) => setSpreadBps(Number(e.target.value))}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="label-caps" htmlFor="mm-size">
            Clip (USD)
          </Label>
          <Input
            id="mm-size"
            type="number"
            value={sizeUsd}
            min={1}
            onChange={(e) => setSizeUsd(Number(e.target.value))}
          />
        </div>
        <div className="flex items-end">
          <Button
            className="w-full"
            variant={running ? "destructive" : "default"}
            onClick={() => setRunning(!running)}
          >
            {running ? "Stop quoting" : "Start quoting"}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-px border-y border-border bg-border sm:grid-cols-4">
        {[
          ["Bid", mm.bid ? mm.bid.toFixed(2) : "—"],
          ["Mid", mm.price ? mm.price.toFixed(2) : "—"],
          ["Ask", mm.ask ? mm.ask.toFixed(2) : "—"],
          ["Inventory", mm.inventory.toFixed(5)],
        ].map(([k, v]) => (
          <div key={k} className="bg-card px-4 py-3">
            <div className="label-caps">{k}</div>
            <div className="tape mt-1 text-sm">{v}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-px bg-border sm:grid-cols-4">
        {[
          ["Realized P&L", usd(mm.realizedPnl)],
          ["Unrealized", usd(mm.unrealizedPnl)],
          ["Stored P&L (24h)", usd(stats?.totalPnl ?? 0)],
          ["Stored trades", String(stats?.trades ?? 0)],
        ].map(([k, v]) => (
          <div key={k} className="bg-card px-4 py-3">
            <div className="label-caps">{k}</div>
            <div className="tape mt-1 text-sm">{v}</div>
          </div>
        ))}
      </div>

      {stats && stats.equityCurve.length > 1 ? (
        <div className="h-32 px-2 pt-3">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={stats.equityCurve}>
              <YAxis hide domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }}
                labelFormatter={(l) => new Date(String(l)).toLocaleTimeString()}
              />
              <Line type="monotone" dataKey="pnl" dot={false} strokeWidth={1.5} stroke="currentColor" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : null}

      <ul className="max-h-48 divide-y divide-border/60 overflow-y-auto border-t border-border">
        {mm.fills.length === 0 ? (
          <li className="tape px-4 py-3 text-[11px] text-muted-foreground">
            No simulated fills yet — start quoting to trade the spread.
          </li>
        ) : (
          mm.fills.map((f) => (
            <li key={f.ts} className="tape flex items-center gap-3 px-4 py-2 text-[11px]">
              <span className="text-muted-foreground">
                {new Date(f.ts).toISOString().slice(11, 19)}
              </span>
              <span className={f.side === "BUY" ? "text-up" : "text-down"}>{f.side}</span>
              <span>{f.price.toFixed(2)}</span>
              <span className="text-muted-foreground">{f.size.toFixed(5)}</span>
              <span className={`ml-auto ${f.pnl >= 0 ? "text-up" : "text-down"}`}>{usd(f.pnl)}</span>
            </li>
          ))
        )}
      </ul>
    </Panel>
  );
}

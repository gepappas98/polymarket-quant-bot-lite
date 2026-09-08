import { Badge } from "@/components/ui/badge";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { Panel, usd } from "@/components/dashboard/Panels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getMmStats } from "@/lib/trading.functions";
import { usePolymarketMarketMaker } from "@/simulation/usePolymarketMarketMaker";

export function MarketMakingPanel() {
  const [marketId, setMarketId] = useState("");
  const [tokenId, setTokenId] = useState("");
  const [spreadBps, setSpreadBps] = useState(8);
  const [sizeUsd, setSizeUsd] = useState(25);
  const [running, setRunning] = useState(false);
  const market = `${marketId}:${tokenId}`;
  const mm = usePolymarketMarketMaker({ marketId, tokenId, spreadBps, sizeUsd, running, cooldownSeconds: 120 });
  const statsFn = useServerFn(getMmStats);
  const { data: stats } = useQuery({
    queryKey: ["mm-stats", market, mm.fills.length],
    queryFn: () => statsFn({ data: { market, timeframeHours: 24 } }),
    enabled: Boolean(marketId && tokenId),
    refetchInterval: 30_000,
  });
  const offline = !mm.connected || mm.stale || !mm.book;

  return (
    <Panel
      title="Polymarket market making"
      hint={offline ? "OFFLINE / NO DATA" : "REAL CLOB L2 live"}
      className="overflow-hidden"
    >
      <div className="flex flex-wrap gap-2 px-4 pt-4">
        <Badge variant="outline">REAL_POLYMARKET_CLOB_WS</Badge>
        <Badge variant="outline">PAPER</Badge>
        <Badge variant="outline">fills: SIMULATED</Badge>
      </div>
      <p className="px-4 pt-2 text-[11px] text-muted-foreground">
        Historical/market data is real Polymarket CLOB data; executions are paper simulations only.
      </p>
      <div className="grid gap-3 px-4 py-4 sm:grid-cols-4">
        <div className="space-y-1.5 sm:col-span-2">
          <Label className="label-caps" htmlFor="mm-market-id">Market ID</Label>
          <Input id="mm-market-id" value={marketId} placeholder="condition/market id" onChange={(e) => setMarketId(e.target.value.trim())} />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label className="label-caps" htmlFor="mm-token-id">Token ID</Label>
          <Input id="mm-token-id" value={tokenId} placeholder="outcome token id" onChange={(e) => setTokenId(e.target.value.trim())} />
        </div>
        <div className="space-y-1.5">
          <Label className="label-caps" htmlFor="mm-spread">Spread (bps)</Label>
          <Input id="mm-spread" type="number" value={spreadBps} min={1} onChange={(e) => setSpreadBps(Number(e.target.value))} />
        </div>
        <div className="space-y-1.5">
          <Label className="label-caps" htmlFor="mm-size">Paper clip (USD)</Label>
          <Input id="mm-size" type="number" value={sizeUsd} min={1} onChange={(e) => setSizeUsd(Number(e.target.value))} />
        </div>
        <div className="flex items-end sm:col-span-2">
          <Button className="w-full" variant={running ? "destructive" : "default"} disabled={!marketId || !tokenId} onClick={() => setRunning(!running)}>
            {running ? "Stop paper quoting" : "Start paper quoting"}
          </Button>
        </div>
      </div>

      {offline ? (
        <div className="border-y border-amber-500/40 bg-amber-500/10 px-4 py-3 text-xs text-amber-200">
          OFFLINE / NO DATA — no replacement prices or synthetic liquidity will be generated.
        </div>
      ) : null}
      <div className="grid grid-cols-2 gap-px border-y border-border bg-border sm:grid-cols-5">
        {[
          ["Best bid", mm.bestBid === null ? "—" : mm.bestBid.toFixed(4)],
          ["Mid", mm.mid === null ? "—" : mm.mid.toFixed(4)],
          ["Best ask", mm.bestAsk === null ? "—" : mm.bestAsk.toFixed(4)],
          ["Spread", mm.spread === null ? "—" : mm.spread.toFixed(4)],
          ["Status", mm.stale ? "STALE" : "LIVE"],
        ].map(([k, v]) => <div key={k} className="bg-card px-4 py-3"><div className="label-caps">{k}</div><div className="tape mt-1 text-sm">{v}</div></div>)}
      </div>
      <div className="grid grid-cols-2 gap-px border-b border-border bg-border sm:grid-cols-4">
        {[
          ["Bid depth", mm.bidDepth.toFixed(4)],
          ["Ask depth", mm.askDepth.toFixed(4)],
          ["Inventory", mm.inventory.toFixed(5)],
          ["Timestamp", mm.book?.timestamp ? new Date(Number(mm.book.timestamp)).toISOString() : "—"],
        ].map(([k, v]) => <div key={k} className="bg-card px-4 py-3"><div className="label-caps">{k}</div><div className="tape mt-1 truncate text-sm">{v}</div></div>)}
      </div>
      <div className="grid grid-cols-2 gap-px bg-border sm:grid-cols-4">
        {[
          ["Realized P&L", usd(mm.realizedPnl)],
          ["Unrealized", usd(mm.unrealizedPnl)],
          ["Stored P&L (24h)", usd(stats?.totalPnl ?? 0)],
          ["Stored trades", String(stats?.trades ?? 0)],
        ].map(([k, v]) => <div key={k} className="bg-card px-4 py-3"><div className="label-caps">{k}</div><div className="tape mt-1 text-sm">{v}</div></div>)}
      </div>
      {stats && stats.equityCurve.length > 1 ? <div className="h-32 px-2 pt-3"><ResponsiveContainer width="100%" height="100%"><LineChart data={stats.equityCurve}><YAxis hide domain={["auto", "auto"]} /><Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} labelFormatter={(l) => new Date(String(l)).toLocaleTimeString()} /><Line type="monotone" dataKey="pnl" dot={false} strokeWidth={1.5} stroke="currentColor" /></LineChart></ResponsiveContainer></div> : null}
      <ul className="max-h-48 divide-y divide-border/60 overflow-y-auto border-t border-border">
        {mm.fills.length === 0 ? <li className="tape px-4 py-3 text-[11px] text-muted-foreground">No SIMULATED fills yet — real CLOB depth is required.</li> : mm.fills.map((f, index) => <li key={`${f.ts}-${index}`} className="tape flex items-center gap-3 px-4 py-2 text-[11px]"><span className="text-muted-foreground">{new Date(f.ts).toISOString().slice(11, 19)}</span><span className="rounded border border-border px-1">PAPER</span><span className={f.side === "BUY" ? "text-up" : "text-down"}>{f.side}</span><span>{f.price.toFixed(4)}</span><span className="text-muted-foreground">{f.size.toFixed(5)}</span><span className="ml-auto text-muted-foreground">SIMULATED</span><span className={f.pnl >= 0 ? "text-up" : "text-down"}>{usd(f.pnl)}</span></li>)}
      </ul>
    </Panel>
  );
}

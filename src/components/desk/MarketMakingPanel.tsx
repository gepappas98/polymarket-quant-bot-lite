import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { Panel, usd } from "@/components/dashboard/Panels";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getMmStats } from "@/lib/trading.functions";
import { usePolymarketMarketMaker } from "@/market-maker/usePolymarketMarketMaker";

const price = (value: number | null) => (value === null ? "NO DATA" : value.toFixed(3));

export function MarketMakingPanel() {
  const [tokenId, setTokenId] = useState("");
  const [marketId, setMarketId] = useState("");
  const [spreadBps, setSpreadBps] = useState(8);
  const [sizeUsd, setSizeUsd] = useState(25);
  const [running, setRunning] = useState(false);
  const mm = usePolymarketMarketMaker({
    tokenId,
    marketId,
    spreadBps,
    sizeUsd,
    running,
    cooldownSeconds: 120,
  });
  const statsFn = useServerFn(getMmStats);
  const { data: stats } = useQuery({
    queryKey: ["mm-stats", marketId, mm.fills.length],
    queryFn: () => statsFn({ data: { market: marketId, timeframeHours: 24 } }),
    enabled: Boolean(marketId),
    refetchInterval: 30_000,
  });
  const hasFreshBook = !mm.stale && mm.bestBid !== null && mm.bestAsk !== null;
  const canQuote = Boolean(tokenId.trim() && marketId.trim() && hasFreshBook);
  const status = !tokenId.trim()
    ? "OFFLINE / NO DATA — enter a Polymarket token ID"
    : !mm.connected
      ? "OFFLINE / NO DATA — CLOB feed disconnected"
      : !hasFreshBook
        ? "OFFLINE / NO DATA — waiting for a fresh L2 book"
        : "REAL POLYMARKET CLOB L2";

  return (
    <Panel title="Polymarket market maker" hint={status} className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 px-4 pt-4">
        <Badge variant="outline">PAPER orders only</Badge>
        <Badge variant="outline">SIMULATED fills only</Badge>
        <span className={`tape text-[10px] uppercase ${hasFreshBook ? "text-up" : "text-warning"}`}>
          {hasFreshBook ? "REAL DATA" : "OFFLINE / NO DATA"}
        </span>
      </div>
      <p className="tape px-4 pt-2 text-[10px] text-muted-foreground">
        Quotes observe public Polymarket CLOB L2. No orders or fills are sent to Polymarket.
      </p>

      <div className="grid gap-3 px-4 py-4 sm:grid-cols-2 lg:grid-cols-5">
        <div className="space-y-1.5">
          <Label className="label-caps" htmlFor="mm-market-id">Market ID</Label>
          <Input id="mm-market-id" value={marketId} placeholder="condition or market ID" onChange={(e) => setMarketId(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label className="label-caps" htmlFor="mm-token-id">Token ID</Label>
          <Input id="mm-token-id" value={tokenId} placeholder="CLOB token_id" onChange={(e) => setTokenId(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label className="label-caps" htmlFor="mm-spread">Spread (bps)</Label>
          <Input id="mm-spread" type="number" value={spreadBps} min={1} onChange={(e) => setSpreadBps(Number(e.target.value))} />
        </div>
        <div className="space-y-1.5">
          <Label className="label-caps" htmlFor="mm-size">Clip (USDC)</Label>
          <Input id="mm-size" type="number" value={sizeUsd} min={1} onChange={(e) => setSizeUsd(Number(e.target.value))} />
        </div>
        <div className="flex items-end">
          <Button className="w-full" variant={running ? "destructive" : "default"} disabled={!running && !canQuote} onClick={() => setRunning((current) => !current)}>
            {running ? "Stop PAPER quoting" : "Start PAPER quoting"}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-px border-y border-border bg-border sm:grid-cols-4 lg:grid-cols-7">
        {[
          ["Best bid", price(mm.bestBid)],
          ["Mid", price(mm.mid)],
          ["Best ask", price(mm.bestAsk)],
          ["Spread", mm.spread === null ? "NO DATA" : mm.spread.toFixed(3)],
          ["Bid depth", hasFreshBook ? mm.bidDepth.toFixed(2) : "NO DATA"],
          ["Ask depth", hasFreshBook ? mm.askDepth.toFixed(2) : "NO DATA"],
          ["Updated", mm.timestamp ? new Date(mm.timestamp).toLocaleTimeString() : "NO DATA"],
        ].map(([label, value]) => <Metric key={label ?? "metric"} label={label ?? ""} value={value ?? ""} />)}
      </div>

      <div className="grid grid-cols-2 gap-px bg-border sm:grid-cols-4">
        <Metric label="PAPER bid" value={price(mm.bid)} />
        <Metric label="PAPER ask" value={price(mm.ask)} />
        <Metric label="PAPER inventory" value={mm.inventory.toFixed(5)} />
        <Metric label="PAPER realized P&L" value={usd(mm.realizedPnl)} />
      </div>

      {stats && stats.equityCurve.length > 1 ? (
        <div className="h-32 px-2 pt-3">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={stats.equityCurve}>
              <YAxis hide domain={["auto", "auto"]} />
              <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} labelFormatter={(label) => new Date(String(label)).toLocaleTimeString()} />
              <Line type="monotone" dataKey="pnl" dot={false} strokeWidth={1.5} stroke="currentColor" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : null}

      <ul className="max-h-48 divide-y divide-border/60 overflow-y-auto border-t border-border">
        {mm.fills.length === 0 ? (
          <li className="tape px-4 py-3 text-[11px] text-muted-foreground">No SIMULATED fills. PAPER quotes require a fresh real Polymarket L2 book.</li>
        ) : mm.fills.map((fill) => (
          <li key={fill.ts} className="tape flex items-center gap-3 px-4 py-2 text-[11px]">
            <Badge variant="outline">SIMULATED</Badge>
            <span className="text-muted-foreground">{new Date(fill.ts).toISOString().slice(11, 19)}</span>
            <span className={fill.side === "BUY" ? "text-up" : "text-down"}>{fill.side} PAPER</span>
            <span>{fill.price.toFixed(3)}</span>
            <span className="text-muted-foreground">{fill.size.toFixed(4)}</span>
            <span className={`ml-auto ${fill.pnl >= 0 ? "text-up" : "text-down"}`}>{usd(fill.pnl)}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="bg-card px-4 py-3"><div className="label-caps">{label}</div><div className="tape mt-1 text-sm">{value}</div></div>;
}

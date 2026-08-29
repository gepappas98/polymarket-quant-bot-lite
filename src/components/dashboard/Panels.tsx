import type { BotStatus, GateRow, LedgerRow, MarketRow } from "@/lib/bot-types";

export function usd(n: number) {
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toFixed(2)}`;
}

function pct(n: number) {
  return `${(n * 100).toFixed(1)}¢`;
}

function clock(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function Panel({
  title,
  hint,
  children,
  className = "",
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <header className="flex items-baseline justify-between gap-3 border-b border-border px-4 py-3">
        <h2 className="label-caps text-foreground">{title}</h2>
        {hint ? <span className="tape text-[10px] text-muted-foreground">{hint}</span> : null}
      </header>
      {children}
    </section>
  );
}

export function StatTile({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "default" | "up" | "down" | "warn";
}) {
  const toneClass =
    tone === "up"
      ? "text-up"
      : tone === "down"
        ? "text-down"
        : tone === "warn"
          ? "text-warn"
          : "text-foreground";
  return (
    <div className="panel px-4 py-3">
      <div className="label-caps">{label}</div>
      <div className={`tape mt-1.5 text-xl font-medium ${toneClass}`}>{value}</div>
      {sub ? <div className="tape mt-1 text-[11px] text-muted-foreground">{sub}</div> : null}
    </div>
  );
}

function SignalBadge({ signal }: { signal: MarketRow["signal"] }) {
  const map: Record<MarketRow["signal"], string> = {
    arb: "border-primary/50 bg-primary/15 text-primary",
    up: "border-up/50 bg-up/15 text-up",
    down: "border-down/50 bg-down/15 text-down",
    flat: "border-border bg-muted text-muted-foreground",
  };
  return (
    <span className={`tape rounded border px-1.5 py-0.5 text-[10px] uppercase ${map[signal]}`}>
      {signal}
    </span>
  );
}

export function MarketsTable({ markets, arbThreshold }: { markets: MarketRow[]; arbThreshold: number }) {
  return (
    <Panel title="Live windows" hint={`arb threshold ${arbThreshold}`} className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left">
          <thead>
            <tr className="label-caps border-b border-border">
              <th className="px-4 py-2 font-normal">Market</th>
              <th className="px-4 py-2 text-right font-normal">Up ask</th>
              <th className="px-4 py-2 text-right font-normal">Down ask</th>
              <th className="px-4 py-2 text-right font-normal">Set cost</th>
              <th className="px-4 py-2 text-right font-normal">Exposure</th>
              <th className="px-4 py-2 text-right font-normal">Closes</th>
              <th className="px-4 py-2 text-right font-normal">Signal</th>
            </tr>
          </thead>
          <tbody>
            {markets.map((m) => {
              const set = m.upAsk + m.downAsk;
              const arb = set <= arbThreshold;
              return (
                <tr key={m.slug + m.windowMinutes} className="border-b border-border/60 last:border-0">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{m.asset}</span>
                      <span className="tape text-[11px] text-muted-foreground">{m.windowMinutes}m</span>
                      {m.cooldownUntil ? (
                        <span className="tape rounded border border-warn/40 bg-warn/10 px-1 py-0.5 text-[9px] uppercase text-warn">
                          cooldown
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td className="tape px-4 py-2.5 text-right text-up">{pct(m.upAsk)}</td>
                  <td className="tape px-4 py-2.5 text-right text-down">{pct(m.downAsk)}</td>
                  <td
                    className={`tape px-4 py-2.5 text-right ${arb ? "text-primary" : "text-muted-foreground"}`}
                  >
                    {set.toFixed(3)}
                  </td>
                  <td className="tape px-4 py-2.5 text-right">{usd(m.exposureUsd)}</td>
                  <td className="tape px-4 py-2.5 text-right text-muted-foreground">
                    {clock(m.secondsToClose)}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <SignalBadge signal={m.signal} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export function GatesPanel({ gates }: { gates: GateRow[] }) {
  return (
    <Panel title="Safety gates" hint="fail closed">
      <ul className="divide-y divide-border/60">
        {gates.map((g) => (
          <li key={g.name} className="flex items-start gap-3 px-4 py-3">
            <span
              className={`mt-1 size-2 shrink-0 rounded-full ${g.allowed ? "bg-up" : "bg-down"}`}
              aria-hidden
            />
            <div className="min-w-0">
              <div className="text-sm font-medium">{g.name}</div>
              <div className="tape mt-0.5 text-[11px] text-muted-foreground">{g.reason}</div>
            </div>
            <span
              className={`tape ml-auto text-[10px] uppercase ${g.allowed ? "text-up" : "text-down"}`}
            >
              {g.allowed ? "pass" : "block"}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function LedgerFeed({ rows }: { rows: LedgerRow[] }) {
  return (
    <Panel title="Ledger feed" hint="data/trades.jsonl" className="overflow-hidden">
      <ul className="max-h-[420px] divide-y divide-border/60 overflow-y-auto">
        {rows.map((r, i) => {
          const tone =
            r.status === "blocked"
              ? "text-down"
              : r.kind === "fill"
                ? "text-up"
                : r.kind === "outcome"
                  ? (r.pnlUsd ?? 0) >= 0
                    ? "text-up"
                    : "text-down"
                  : "text-muted-foreground";
          return (
            <li key={`${r.ts}-${i}`} className="px-4 py-2.5">
              <div className="flex items-center gap-2">
                <span className="tape text-[11px] text-muted-foreground">
                  {new Date(r.ts).toISOString().slice(11, 19)}
                </span>
                <span className={`tape text-[10px] uppercase ${tone}`}>
                  {r.status === "blocked" ? "blocked" : r.kind}
                </span>
                <span className="tape truncate text-[11px]">{r.marketSlug}</span>
                {r.side ? (
                  <span
                    className={`tape text-[10px] ${r.side === "UP" ? "text-up" : "text-down"}`}
                  >
                    {r.side}
                  </span>
                ) : null}
                <span className="tape ml-auto text-[11px]">
                  {r.pnlUsd !== null
                    ? usd(r.pnlUsd)
                    : r.price !== null
                      ? `${pct(r.price)} × ${usd(r.sizeUsd ?? 0)}`
                      : ""}
                </span>
              </div>
              <p className="tape mt-1 truncate text-[10px] text-muted-foreground">{r.reason}</p>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

export function PnlChart({ series }: { series: BotStatus["pnlSeries"] }) {
  const values = series.map((p) => p.cumulativePnl);
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const span = max - min || 1;
  const w = 100;
  const h = 34;
  const points = series.map((p, i) => {
    const x = (i / Math.max(1, series.length - 1)) * w;
    const y = h - ((p.cumulativePnl - min) / span) * h;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const last = values[values.length - 1] ?? 0;
  const zeroY = h - ((0 - min) / span) * h;

  return (
    <Panel title="Session P&L" hint="paper ledger, cumulative">
      <div className="px-4 pb-4 pt-3">
        <div className={`tape text-2xl font-medium ${last >= 0 ? "text-up" : "text-down"}`}>
          {usd(last)}
        </div>
        <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="mt-3 h-28 w-full">
          <line
            x1="0"
            x2={w}
            y1={zeroY}
            y2={zeroY}
            stroke="currentColor"
            className="text-border"
            strokeWidth="0.3"
          />
          <polyline
            points={points.join(" ")}
            fill="none"
            stroke="currentColor"
            className={last >= 0 ? "text-up" : "text-down"}
            strokeWidth="0.8"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </Panel>
  );
}

const BTC_TIP_ADDRESS = "bc1q0d0ccaxuw065ezdulr68azp2fjhc0avaqf0pyz";

export function SupportPanel() {
  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=0&data=${BTC_TIP_ADDRESS}`;
  return (
    <Panel title="Support the developer" hint="btc">
      <div className="flex flex-col items-center gap-4 px-4 py-6 text-center">
        <p className="text-sm font-medium">☕ Found Polymarket Quant Bot useful?</p>
        <p className="max-w-md text-[12px] text-muted-foreground">
          If this tool helped your trading or development workflow, consider tipping the
          developer. Every sat counts. 🙏
        </p>
        <div className="rounded-lg bg-white p-3">
          <img src={qrUrl} alt="BTC tip address QR code" width={220} height={220} />
        </div>
        <div className="label-caps text-muted-foreground">BTC address</div>
        <code className="tape rounded border border-border bg-muted px-3 py-2 text-[12px] break-all">
          {BTC_TIP_ADDRESS}
        </code>
      </div>
      <div className="tape border-t border-border px-4 py-2 text-center text-[10px] text-muted-foreground">
        POLYMARKET QUANT BOT — Built with 🔥 by the developer
      </div>
    </Panel>
  );
}

export function ConfigPanel({ config }: { config: BotStatus["config"] }) {
  const rows: [string, string][] = [
    ["Assets", config.assets.join(" · ")],
    ["Windows", config.windows.map((w) => `${w}m`).join(" · ")],
    ["Max order", usd(config.maxOrderUsd)],
    ["Max market exposure", usd(config.maxMarketExposureUsd)],
    ["Arb threshold", config.arbThreshold.toFixed(3)],
    ["Min directional edge", config.minDirectionalEdge.toFixed(3)],
    ["Daily loss limit", usd(config.dailyLossLimitUsd)],
    ["Cooldown", `${config.cooldownMinutes} min`],
    ["Track record gate", `${config.minTrackRecordWinPct}% / ${config.minTrackRecordSamples} samples`],
    ["Maker preference", config.preferMaker ? "on" : "off"],
  ];
  return (
    <Panel title="Risk configuration" hint=".env">
      <dl className="divide-y divide-border/60">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between gap-4 px-4 py-2.5">
            <dt className="text-sm text-muted-foreground">{k}</dt>
            <dd className="tape text-sm">{v}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  );
}

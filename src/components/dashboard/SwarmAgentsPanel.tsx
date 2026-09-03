import type { SwarmAgentRow, SwarmSnapshot } from "@/lib/bot-types";
import { Panel } from "@/components/dashboard/Panels";
import { Progress } from "@/components/ui/progress";

/** Display order + short role labels (matches bot/swarm.py). */
const AGENT_META: { id: string; role: string }[] = [
  { id: "TIDAL", role: "scanner" },
  { id: "NORO", role: "pricing" },
  { id: "ZEPHR", role: "liquidity" },
  { id: "OKAPI", role: "inventory" },
  { id: "RUNE", role: "risk veto" },
  { id: "VESKA", role: "execution" },
  { id: "MARIN", role: "settlement" },
  { id: "LUMEN", role: "sentiment" },
];

function scoreTone(score: number | null, veto: boolean): string {
  if (veto) return "text-down border-down/50 bg-down/10";
  if (score === null) return "text-muted-foreground border-border bg-muted/40";
  if (score >= 0.75) return "text-up border-up/40 bg-up/10";
  if (score >= 0.5) return "text-foreground border-border bg-muted/30";
  return "text-warn border-warn/40 bg-warn/10";
}

function AgentTile({
  id,
  role,
  row,
  weight,
}: {
  id: string;
  role: string;
  row: SwarmAgentRow | undefined;
  weight: number | undefined;
}) {
  const score = row?.score ?? null;
  const veto = Boolean(row?.veto);
  const pct = score === null ? 0 : Math.round(Math.max(0, Math.min(1, score)) * 100);
  return (
    <div
      className={`rounded border px-3 py-2.5 ${scoreTone(score, veto)}`}
      title={row?.reason || role}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="tape text-[11px] font-semibold tracking-wide">{id}</span>
        {veto ? (
          <span className="tape text-[9px] uppercase text-down">veto</span>
        ) : (
          <span className="tape text-[10px] text-muted-foreground">
            {score === null ? "—" : pct}
          </span>
        )}
      </div>
      <div className="tape mt-0.5 text-[10px] text-muted-foreground">{role}</div>
      <Progress value={veto ? 0 : pct} className="mt-2 h-1" />
      <div className="tape mt-1 truncate text-[9px] text-muted-foreground">
        {veto ? row?.reason || "blocked" : row?.reason || (weight != null ? `w=${weight}` : "idle")}
      </div>
    </div>
  );
}

export function SwarmAgentsPanel({ swarm }: { swarm?: SwarmSnapshot | null | undefined }) {
  if (!swarm) {
    return (
      <Panel title="Swarm agents" hint="module pipeline">
        <p className="tape px-4 py-6 text-[11px] text-muted-foreground">
          No swarm payload. Point{" "}
          <code className="rounded bg-muted px-1">BOT_STATUS_URL</code> at a worker with{" "}
          <code className="rounded bg-muted px-1">SWARM_ENABLED=true</code>, or use the demo feed.
        </p>
      </Panel>
    );
  }

  const consensus = swarm.last?.consensus;
  const ok = swarm.last?.ok;
  const thr = swarm.threshold ?? swarm.last?.threshold ?? 0.7;
  const bar =
    consensus == null ? 0 : Math.round(Math.max(0, Math.min(1, consensus)) * 100);

  return (
    <Panel
      title="Swarm agents"
      hint={
        swarm.enabled
          ? `consensus ≥ ${(thr * 100).toFixed(0)}% · non-LLM modules`
          : "swarm disabled on worker"
      }
    >
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="label-caps">Last consensus</div>
            <div
              className={`tape mt-1 text-lg font-medium ${
                ok === false ? "text-down" : ok ? "text-up" : "text-muted-foreground"
              }`}
            >
              {consensus == null ? "—" : `${(consensus * 100).toFixed(1)}%`}
              <span className="ml-2 text-[11px] text-muted-foreground">
                thr {(thr * 100).toFixed(0)}%
              </span>
            </div>
          </div>
          <span
            className={`tape rounded border px-2 py-1 text-[10px] uppercase ${
              ok === false
                ? "border-down/50 bg-down/15 text-down"
                : ok
                  ? "border-up/50 bg-up/15 text-up"
                  : "border-border bg-muted text-muted-foreground"
            }`}
          >
            {ok === false ? "blocked" : ok ? "pass" : "idle"}
          </span>
        </div>
        <Progress value={bar} className="mt-2 h-1.5" />
        {swarm.last?.detail ? (
          <p className="tape mt-2 text-[10px] text-muted-foreground">{swarm.last.detail}</p>
        ) : null}
        {swarm.last?.veto_by?.length ? (
          <p className="tape mt-1 text-[10px] text-down">
            veto: {swarm.last.veto_by.join(", ")}
          </p>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-4">
        {AGENT_META.map(({ id, role }) => (
          <AgentTile
            key={id}
            id={id}
            role={role}
            row={swarm.agents?.[id]}
            weight={swarm.weights?.[id]}
          />
        ))}
      </div>
    </Panel>
  );
}

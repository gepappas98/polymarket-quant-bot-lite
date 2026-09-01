import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { toast } from "sonner";
import { Panel } from "@/components/dashboard/Panels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { supabase } from "@/integrations/supabase/client";
import { sendAlert } from "@/lib/trading.functions";

const TYPES = ["kill_switch", "daily_loss", "drawdown", "win_rate"];
const CHANNELS = ["slack", "telegram", "email"];

export function AlertConfigPanel() {
  const qc = useQueryClient();
  const send = useServerFn(sendAlert);
  const [type, setType] = useState(TYPES[0]!);
  const [channel, setChannel] = useState(CHANNELS[0]!);
  const [threshold, setThreshold] = useState(50);
  const [destination, setDestination] = useState("");

  const { data: configs } = useQuery({
    queryKey: ["alert-config"],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("alert_config")
        .select("id, type, channel, threshold, destination, active")
        .order("created_at", { ascending: false });
      if (error) throw error;
      return data;
    },
  });

  const { data: history } = useQuery({
    queryKey: ["alert-history"],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("alert_history")
        .select("id, message, triggered_at, resolved")
        .order("triggered_at", { ascending: false })
        .limit(20);
      if (error) throw error;
      return data;
    },
  });

  async function add() {
    const { data: auth } = await supabase.auth.getUser();
    const { error } = await supabase.from("alert_config").insert({
      user_id: auth.user!.id,
      type,
      channel,
      threshold,
      destination: destination.trim() || null,
    });
    if (error) {
      toast.error(error.message);
      return;
    }
    setDestination("");
    toast.success("Alert rule created");
    void qc.invalidateQueries({ queryKey: ["alert-config"] });
  }

  return (
    <Panel title="Alerting" hint="kill-switch & loss monitors">
      <div className="grid gap-3 px-4 py-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label className="label-caps">Trigger</Label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
          >
            {TYPES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label className="label-caps">Channel</Label>
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
            className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
          >
            {CHANNELS.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label className="label-caps" htmlFor="al-threshold">
            Threshold
          </Label>
          <Input
            id="al-threshold"
            type="number"
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="label-caps" htmlFor="al-dest">
            Webhook URL
          </Label>
          <Input
            id="al-dest"
            placeholder="https://hooks.slack.com/…"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
          />
        </div>
      </div>
      <div className="px-4 pb-4">
        <Button onClick={add}>Add rule</Button>
      </div>

      <ul className="divide-y divide-border/60 border-y border-border">
        {(configs ?? []).length === 0 ? (
          <li className="tape px-4 py-3 text-[11px] text-muted-foreground">No alert rules yet.</li>
        ) : (
          (configs ?? []).map((c) => (
            <li key={c.id} className="flex items-center gap-3 px-4 py-2.5">
              <span
                className={`size-2 rounded-full ${c.active ? "bg-up" : "bg-muted-foreground"}`}
                aria-hidden
              />
              <div className="min-w-0">
                <div className="text-sm">
                  {c.type} <span className="text-muted-foreground">via {c.channel}</span>
                </div>
                <div className="tape text-[10px] text-muted-foreground">threshold {c.threshold}</div>
              </div>
              <div className="ml-auto flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={async () => {
                    const res = await send({
                      data: { configId: c.id, message: `Test alert for ${c.type}` },
                    });
                    if (res.delivered) toast.success("Test alert delivered");
                    else toast.warning(res.error ?? "Alert recorded without delivery");
                    void qc.invalidateQueries({ queryKey: ["alert-history"] });
                  }}
                >
                  Test
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={async () => {
                    await supabase.from("alert_config").update({ active: !c.active }).eq("id", c.id);
                    void qc.invalidateQueries({ queryKey: ["alert-config"] });
                  }}
                >
                  {c.active ? "Disable" : "Enable"}
                </Button>
              </div>
            </li>
          ))
        )}
      </ul>

      <ul className="max-h-52 divide-y divide-border/60 overflow-y-auto">
        {(history ?? []).map((h) => (
          <li key={h.id} className="tape flex items-start gap-3 px-4 py-2 text-[11px]">
            <span className="text-muted-foreground">
              {new Date(h.triggered_at).toISOString().slice(5, 19).replace("T", " ")}
            </span>
            <span className="min-w-0 flex-1">{h.message}</span>
            <span className={h.resolved ? "text-up" : "text-warn"}>
              {h.resolved ? "resolved" : "open"}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

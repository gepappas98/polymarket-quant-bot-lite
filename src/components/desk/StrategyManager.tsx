import { Suspense, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Panel } from "@/components/dashboard/Panels";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { supabase } from "@/integrations/supabase/client";
import { strategies, type StrategyParams } from "@/strategies/registry";

export function StrategyManager() {
  const qc = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, StrategyParams>>({});

  const { data: configs } = useQuery({
    queryKey: ["strategy-config"],
    queryFn: async () => {
      const { data, error } = await supabase.from("strategy_config").select("id, name, enabled, parameters");
      if (error) throw error;
      return data;
    },
  });

  async function save(name: string, enabled: boolean, parameters: StrategyParams) {
    const { data: auth } = await supabase.auth.getUser();
    const { error } = await supabase
      .from("strategy_config")
      .upsert({ user_id: auth.user!.id, name, enabled, parameters }, { onConflict: "user_id,name" });
    if (error) {
      toast.error(error.message);
      return;
    }
    toast.success("Strategy saved");
    void qc.invalidateQueries({ queryKey: ["strategy-config"] });
  }

  return (
    <Panel title="Strategies" hint="lazy-loaded plugins">
      <ul className="divide-y divide-border/60">
        {strategies.map((s) => {
          const cfg = configs?.find((c) => c.name === s.id);
          const params = draft[s.id] ?? ((cfg?.parameters as StrategyParams | null) ?? s.defaults);
          const enabled = cfg?.enabled ?? false;
          return (
            <li key={s.id} className="px-4 py-3">
              <div className="flex items-center gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium">{s.name}</div>
                  <div className="tape text-[10px] text-muted-foreground">{s.description}</div>
                </div>
                <div className="ml-auto flex items-center gap-3">
                  <Switch checked={enabled} onCheckedChange={(v) => void save(s.id, v, params)} />
                  <Button size="sm" variant="outline" onClick={() => setOpen(open === s.id ? null : s.id)}>
                    {open === s.id ? "Hide" : "Params"}
                  </Button>
                </div>
              </div>
              {open === s.id ? (
                <div className="mt-3 rounded-md border border-border p-3">
                  <Suspense
                    fallback={<p className="tape text-[11px] text-muted-foreground">Loading editor…</p>}
                  >
                    <s.Panel
                      params={params}
                      onChange={(next) => setDraft((d) => ({ ...d, [s.id]: next }))}
                    />
                  </Suspense>
                  <Button className="mt-3" size="sm" onClick={() => void save(s.id, enabled, params)}>
                    Save parameters
                  </Button>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

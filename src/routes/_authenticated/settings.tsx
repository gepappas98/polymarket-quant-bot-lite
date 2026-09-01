import { useEffect, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { NavLinks } from "@/components/dashboard/NavLinks";
import { Panel } from "@/components/dashboard/Panels";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  getRiskConfig,
  riskQueryKeys,
  updateRiskConfig,
  type RiskConfig,
  type RiskConfigUpdate,
} from "@/lib/riskApi";

export const Route = createFileRoute("/_authenticated/settings")({
  head: () => ({
    meta: [
      { title: "Settings — Polymarket Quant Bot" },
      { name: "description", content: "Configure advanced risk engine limits and safety gates." },
    ],
  }),
  component: SettingsPage,
});

type RiskForm = Required<RiskConfigUpdate>;

const defaults: RiskForm = {
  daily_loss_limit: -200,
  cooldown_seconds: 180,
  enabled_time_start: "00:00",
  enabled_time_end: "23:59",
  category_ceiling_politics: 500,
  category_ceiling_sports: 500,
  k_value: 0.25,
  max_position_pct: 0.05,
  trailing_stop_pct: 5,
  enable_circuit_breaker: true,
  enable_time_window: false,
  enable_category_ceiling: false,
  enable_trailing_stop: false,
};

function SettingsPage() {
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: riskQueryKeys.risk(), queryFn: getRiskConfig });
  const [form, setForm] = useState<RiskForm>(defaults);
  const [loaded, setLoaded] = useState<RiskForm>(defaults);
  const [validationError, setValidationError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!config.data) return;
    const next = toForm(config.data);
    setForm(next);
    setLoaded(next);
  }, [config.data]);

  const save = useMutation({
    mutationFn: (changed: RiskConfigUpdate) => updateRiskConfig(changed),
    onSuccess: (next) => {
      queryClient.setQueryData(riskQueryKeys.risk(), next);
      setLoaded(toForm(next));
      setSaved(true);
      toast.success("Risk settings saved");
    },
  });

  function update<K extends keyof RiskForm>(key: K, value: RiskForm[K]) {
    setSaved(false);
    setForm((current) => ({ ...current, [key]: value }));
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!isTime(form.enabled_time_start) || !isTime(form.enabled_time_end)) {
      setValidationError("Trading window must use HH:MM format.");
      return;
    }
    setValidationError("");
    const changed = Object.fromEntries(
      (Object.keys(form) as (keyof RiskForm)[])
        .filter((key) => form[key] !== loaded[key])
        .map((key) => [key, form[key]]),
    ) as RiskConfigUpdate;
    if (Object.keys(changed).length === 0) {
      setSaved(true);
      return;
    }
    save.mutate(changed);
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:py-10">
      <header className="panel mb-6 flex flex-wrap items-center gap-4 px-4 py-4">
        <div>
          <h1 className="text-lg font-bold tracking-tight sm:text-xl">Risk settings</h1>
          <p className="tape mt-1 text-[11px] text-muted-foreground">
            persistent limits used by sizing and admission gates
          </p>
        </div>
        <div className="ml-auto">
          <NavLinks />
        </div>
      </header>

      {config.isError ? <OfflineNotice /> : null}
      <Panel title="Risk configuration" hint="advanced engine">
        <form onSubmit={submit} className="grid gap-5 px-4 py-5 md:grid-cols-2">
          <NumberField
            label="Daily loss limit (USDC)"
            value={form.daily_loss_limit}
            onChange={(v) => update("daily_loss_limit", v)}
          />
          <NumberField
            label="Cooldown (seconds)"
            value={form.cooldown_seconds}
            onChange={(v) => update("cooldown_seconds", v)}
          />
          <TimeField
            label="Enabled time start"
            value={form.enabled_time_start}
            onChange={(v) => update("enabled_time_start", v)}
          />
          <TimeField
            label="Enabled time end"
            value={form.enabled_time_end}
            onChange={(v) => update("enabled_time_end", v)}
          />
          <NumberField
            label="Politics ceiling (USDC)"
            value={form.category_ceiling_politics}
            onChange={(v) => update("category_ceiling_politics", v)}
          />
          <NumberField
            label="Sports ceiling (USDC)"
            value={form.category_ceiling_sports}
            onChange={(v) => update("category_ceiling_sports", v)}
          />
          <NumberField
            label="Kelly k value"
            value={form.k_value}
            step={0.01}
            onChange={(v) => update("k_value", v)}
          />
          <NumberField
            label="Max position percentage"
            value={form.max_position_pct}
            step={0.005}
            onChange={(v) => update("max_position_pct", v)}
          />
          <NumberField
            label="Trailing stop percentage"
            value={form.trailing_stop_pct}
            onChange={(v) => update("trailing_stop_pct", v)}
          />
          <Toggle
            label="Enable circuit breaker"
            checked={form.enable_circuit_breaker}
            onChange={(v) => update("enable_circuit_breaker", v)}
          />
          <Toggle
            label="Enable time window"
            checked={form.enable_time_window}
            onChange={(v) => update("enable_time_window", v)}
          />
          <Toggle
            label="Enable category ceiling"
            checked={form.enable_category_ceiling}
            onChange={(v) => update("enable_category_ceiling", v)}
          />
          <Toggle
            label="Enable trailing stop"
            checked={form.enable_trailing_stop}
            onChange={(v) => update("enable_trailing_stop", v)}
          />
          {validationError ? (
            <p className="text-sm text-down md:col-span-2">{validationError}</p>
          ) : null}
          {save.isError ? (
            <p className="text-sm text-down md:col-span-2">{save.error.message}</p>
          ) : null}
          <div className="flex items-center gap-3 md:col-span-2">
            <button
              type="submit"
              disabled={save.isPending}
              className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
            >
              {save.isPending ? "Saving…" : "Save settings"}
            </button>
            {saved ? <span className="tape text-xs text-up">Saved</span> : null}
          </div>
        </form>
      </Panel>
    </main>
  );
}

function toForm(config: RiskConfig): RiskForm {
  return {
    daily_loss_limit: config.daily_loss_limit,
    cooldown_seconds: config.cooldown_seconds,
    enabled_time_start: config.enabled_time_start,
    enabled_time_end: config.enabled_time_end,
    category_ceiling_politics: config.category_ceiling_politics,
    category_ceiling_sports: config.category_ceiling_sports,
    k_value: config.k_value,
    max_position_pct: config.max_position_pct,
    trailing_stop_pct: config.trailing_stop_pct,
    enable_circuit_breaker: config.enable_circuit_breaker,
    enable_time_window: config.enable_time_window,
    enable_category_ceiling: config.enable_category_ceiling,
    enable_trailing_stop: config.enable_trailing_stop,
  };
}

function NumberField({
  label,
  value,
  step = 1,
  onChange,
}: {
  label: string;
  value: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="label-caps">{label}</Label>
      <Input
        type="number"
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  );
}

function TimeField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="label-caps">{label}</Label>
      <Input type="time" value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2">
      <Label className="text-sm">{label}</Label>
      <Switch checked={checked} onCheckedChange={onChange} aria-label={label} />
    </div>
  );
}

function isTime(value: string) {
  return /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value);
}

function OfflineNotice() {
  return (
    <div className="mb-3 rounded-md border border-warn/40 bg-warn/10 px-4 py-3 tape text-[11px] text-warn">
      API offline — start <code>uvicorn app.main:app</code>
    </div>
  );
}

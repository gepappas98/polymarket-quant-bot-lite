import { useEffect, useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { NavLinks } from "@/components/dashboard/NavLinks";
import { Panel, usd } from "@/components/dashboard/Panels";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import {
  calculateSizing,
  getRiskConfig,
  riskQueryKeys,
  updateRiskConfig,
  type KellySizingRequest,
} from "@/lib/riskApi";
import { kellyFraction, kellySizeUsd } from "@/lib/kelly";

export const Route = createFileRoute("/sizing")({
  head: () => ({
    meta: [
      { title: "Sizing — Polymarket Quant Bot" },
      { name: "description", content: "Calculate fractional Kelly position sizes with risk caps." },
    ],
  }),
  component: SizingPage,
});

const categories = ["politics", "sports", "crypto", "other"] as const;

function SizingPage() {
  const queryClient = useQueryClient();
  const config = useQuery({
    queryKey: riskQueryKeys.risk(),
    queryFn: getRiskConfig,
  });
  const [balance, setBalance] = useState(1000);
  const [confidence, setConfidence] = useState(0.65);
  const [price, setPrice] = useState(0.5);
  const [category, setCategory] = useState("crypto");
  const [varianceText, setVarianceText] = useState("");
  const [kValue, setKValue] = useState(0.25);
  const [maxPositionPct, setMaxPositionPct] = useState(0.05);

  useEffect(() => {
    if (config.data) {
      setKValue(config.data.k_value);
      setMaxPositionPct(config.data.max_position_pct);
    }
  }, [config.data]);

  const request = useMemo<KellySizingRequest>(() => {
    const base: KellySizingRequest = {
      balance,
      confidence,
      category,
      price,
      k_value: kValue,
      max_position_pct: maxPositionPct,
    };
    if (varianceText.trim()) base.variance = Number(varianceText);
    return base;
  }, [balance, category, confidence, kValue, maxPositionPct, price, varianceText]);

  const [debouncedRequest, setDebouncedRequest] = useState(request);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedRequest(request), 300);
    return () => window.clearTimeout(timer);
  }, [request]);

  const sizing = useQuery({
    queryKey: riskQueryKeys.sizing(debouncedRequest),
    queryFn: () => calculateSizing(debouncedRequest),
    placeholderData: keepPreviousData,
  });
  const save = useMutation({
    mutationFn: () => updateRiskConfig({ k_value: kValue, max_position_pct: maxPositionPct }),
    onSuccess: (next) => {
      queryClient.setQueryData(riskQueryKeys.risk(), next);
      toast.success("Sizing limits saved");
    },
  });

  const localKelly = kellyFraction(confidence, price);
  const localFraction = Math.min(localKelly * kValue, maxPositionPct);
  const localSize = kellySizeUsd({
    winProb: confidence,
    price,
    bankrollUsd: balance,
    fractionOfKelly: kValue,
    maxOrderUsd: Number.POSITIVE_INFINITY,
  });

  return (
    <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:py-10">
      <header className="panel mb-6 flex flex-wrap items-center gap-4 px-4 py-4">
        <div>
          <h1 className="text-lg font-bold tracking-tight sm:text-xl">Risk sizing</h1>
          <p className="tape mt-1 text-[11px] text-muted-foreground">
            fractional Kelly with category-aware variance caps
          </p>
        </div>
        <div className="ml-auto">
          <NavLinks />
        </div>
      </header>

      {config.isError || sizing.isError ? <OfflineNotice /> : null}
      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Sizing inputs" hint="live preview">
          <div className="grid gap-4 px-4 py-4">
            <NumberField label="Balance (USDC)" value={balance} step={10} onChange={setBalance} />
            <SliderField
              label={`Confidence · ${(confidence * 100).toFixed(0)}%`}
              value={confidence}
              min={0.5}
              max={0.95}
              step={0.01}
              onChange={setConfidence}
            />
            <SliderField
              label={`Price · ${price.toFixed(2)} (odds ${(1 / price).toFixed(2)})`}
              value={price}
              min={0.05}
              max={0.95}
              step={0.01}
              onChange={setPrice}
            />
            <div className="space-y-1.5">
              <Label className="label-caps">Category</Label>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {categories.map((item) => (
                    <SelectItem key={item} value={item}>
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="label-caps">Optional variance</Label>
              <Input
                type="number"
                step={0.01}
                value={varianceText}
                placeholder="auto from recent fills"
                onChange={(event) => setVarianceText(event.target.value)}
              />
            </div>
            <SliderField
              label={`k value · ${kValue.toFixed(2)}`}
              value={kValue}
              min={0}
              max={1}
              step={0.01}
              onChange={setKValue}
            />
            <SliderField
              label={`Max position · ${(maxPositionPct * 100).toFixed(1)}%`}
              value={maxPositionPct}
              min={0}
              max={0.25}
              step={0.005}
              onChange={setMaxPositionPct}
            />
            <Button onClick={() => save.mutate()} disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save k / max% to risk config"}
            </Button>
            {save.isError ? <p className="text-xs text-down">{save.error.message}</p> : null}
          </div>
        </Panel>

        <Panel title="Sizing preview" hint="risk API">
          <div className="grid grid-cols-2 gap-px border-b border-border bg-border">
            <Metric
              label="Suggested size"
              value={sizing.data ? usd(sizing.data.suggested_size) : "—"}
            />
            <Metric
              label="f value"
              value={sizing.data ? `${sizing.data.f_value.toFixed(4)}%` : "—"}
            />
            <Metric label="Raw Kelly" value={sizing.data?.raw_kelly.toFixed(4) ?? "—"} />
            <Metric label="Variance used" value={sizing.data?.variance_used?.toFixed(4) ?? "—"} />
          </div>
          <div className="flex items-center justify-between gap-3 px-4 py-4">
            <span className="label-caps">Cap applied</span>
            {sizing.data?.capped_by ? (
              <Badge variant="outline">{sizing.data.capped_by}</Badge>
            ) : (
              <span className="tape text-xs text-muted-foreground">none</span>
            )}
          </div>
          <div className="border-t border-border px-4 py-4">
            <div className="label-caps">Local estimate</div>
            <div className="mt-2 flex items-baseline justify-between gap-3">
              <span className="tape text-lg">
                {usd(Math.min(localSize, balance * maxPositionPct))}
              </span>
              <span className="tape text-xs text-muted-foreground">
                {(localFraction * 100).toFixed(4)}% · f* {localKelly.toFixed(4)}
              </span>
            </div>
          </div>
        </Panel>
      </div>
    </main>
  );
}

function NumberField({
  label,
  value,
  step,
  onChange,
  placeholder,
}: {
  label: string;
  value: number | string;
  step: number;
  onChange: (value: number) => void;
  placeholder?: string;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="label-caps">{label}</Label>
      <Input
        type="number"
        step={step}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  );
}

function SliderField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <div>
      <Label className="label-caps">{label}</Label>
      <Slider
        className="mt-3"
        value={[value]}
        min={min}
        max={max}
        step={step}
        onValueChange={(values) => onChange(values[0] ?? value)}
      />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card px-4 py-3">
      <div className="label-caps">{label}</div>
      <div className="tape mt-1 text-sm">{value}</div>
    </div>
  );
}

function OfflineNotice() {
  return (
    <div className="mb-3 rounded-md border border-warn/40 bg-warn/10 px-4 py-3 tape text-[11px] text-warn">
      API offline — start <code>uvicorn app.main:app</code>
    </div>
  );
}

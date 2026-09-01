import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Panel, usd } from "@/components/dashboard/Panels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  calculateSizing,
  getApiStatus,
  riskQueryKeys,
  type KellySizingResponse,
} from "@/lib/riskApi";

const categories = ["politics", "sports", "crypto", "other"];

export function SimulateTradeWidget() {
  const [balance, setBalance] = useState(1000);
  const [confidence, setConfidence] = useState(0.65);
  const [price, setPrice] = useState(0.5);
  const [category, setCategory] = useState("crypto");
  const status = useQuery({
    queryKey: riskQueryKeys.status(),
    queryFn: getApiStatus,
    refetchInterval: 10_000,
  });
  const sizing = useMutation<KellySizingResponse, Error>({
    mutationFn: () =>
      calculateSizing({
        balance,
        confidence,
        category,
        price,
      }),
  });

  return (
    <Panel title="Simulate trade" hint="risk API">
      <div className="grid gap-3 px-4 py-4 sm:grid-cols-2">
        <Field label="Balance (USDC)" value={balance} onChange={setBalance} />
        <Field label="Confidence" value={confidence} step={0.01} onChange={setConfidence} />
        <Field label="Price" value={price} step={0.01} onChange={setPrice} />
        <div className="space-y-1.5">
          <Label className="label-caps">Category</Label>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
          >
            {categories.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="flex items-center gap-3 border-t border-border px-4 py-3">
        <Button size="sm" onClick={() => sizing.mutate()} disabled={sizing.isPending}>
          {sizing.isPending ? "Calculating…" : "Calculate size"}
        </Button>
        {sizing.data ? (
          <span className="tape text-xs text-up">
            {usd(sizing.data.suggested_size)} · {sizing.data.f_value.toFixed(4)}% f
          </span>
        ) : null}
      </div>
      {sizing.isError ? (
        <p className="px-4 pb-3 tape text-[11px] text-warn">risk API offline</p>
      ) : null}
      <div className="border-t border-border px-4 py-3">
        {status.isError ? (
          <p className="tape text-[11px] text-warn">risk API offline</p>
        ) : status.data ? (
          <div className="space-y-2">
            <StatusRow
              label="Circuit breaker"
              status={status.data.circuit_breaker.status}
              detail={`${usd(status.data.daily_pnl)} daily pnl · limit ${usd(Number(status.data.circuit_breaker.detail["limit"] ?? 0))}`}
            />
            <StatusRow
              label="Time window"
              status={status.data.time_window.status}
              detail={status.data.time_window.reason}
            />
            <div className="flex flex-wrap gap-1.5 pt-1">
              {status.data.active_strategies.length ? (
                status.data.active_strategies.map((strategy) => (
                  <span
                    key={strategy}
                    className="tape rounded border border-primary/40 bg-primary/10 px-1.5 py-0.5 text-[10px] uppercase text-primary"
                  >
                    {strategy}
                  </span>
                ))
              ) : (
                <span className="tape text-[10px] text-muted-foreground">
                  all strategies active
                </span>
              )}
            </div>
          </div>
        ) : (
          <p className="tape text-[11px] text-muted-foreground">Loading risk status…</p>
        )}
      </div>
    </Panel>
  );
}

function Field({
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

function StatusRow({ label, status, detail }: { label: string; status: string; detail: string }) {
  const tone = status === "OK" ? "text-up" : status === "BLOCKED" ? "text-down" : "text-warn";
  return (
    <div className="flex items-start gap-2">
      <span className={`tape text-[10px] uppercase ${tone}`}>{status}</span>
      <div>
        <div className="text-xs font-medium">{label}</div>
        <div className="tape text-[10px] text-muted-foreground">{detail}</div>
      </div>
    </div>
  );
}

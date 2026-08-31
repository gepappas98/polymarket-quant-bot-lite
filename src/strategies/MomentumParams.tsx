import type { StrategyParams } from "./registry";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function MomentumParams({
  params,
  onChange,
}: {
  params: StrategyParams;
  onChange: (next: StrategyParams) => void;
}) {
  const fields: [string, string][] = [
    ["fast", "Fast SMA"],
    ["slow", "Slow SMA"],
    ["stakeUsd", "Stake (USD)"],
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {fields.map(([key, label]) => (
        <div key={key} className="space-y-1.5">
          <Label htmlFor={`mom-${key}`} className="label-caps">
            {label}
          </Label>
          <Input
            id={`mom-${key}`}
            type="number"
            value={params[key] ?? 0}
            onChange={(e) => onChange({ ...params, [key]: Number(e.target.value) })}
          />
        </div>
      ))}
    </div>
  );
}

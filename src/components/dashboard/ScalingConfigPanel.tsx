import { useQuery } from "@tanstack/react-query";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Panel, usd } from "@/components/dashboard/Panels";
import { analyticsQueryKeys, getMarketsSnapshot } from "@/lib/riskApi";
import { kellySizeUsd } from "@/lib/kelly";

export function ScalingConfigPanel({
  balance,
  maxPositionPct,
  onMaxPositionPct,
  kValue,
  pyramiding,
  onPyramiding,
}: {
  balance: number;
  maxPositionPct: number;
  onMaxPositionPct: (value: number) => void;
  kValue: number;
  pyramiding: boolean;
  onPyramiding: (value: boolean) => void;
}) {
  const snapshot = useQuery({
    queryKey: analyticsQueryKeys.snapshot(),
    queryFn: () => getMarketsSnapshot(),
    staleTime: 30_000,
  });
  const open = (snapshot.data ?? []).filter((row) => row.open_positions > 0);
  const cap = balance * maxPositionPct;

  return (
    <Panel title="Scaling configuration" hint="position ramp controls">
      <div className="grid gap-4 px-4 py-4">
        <div>
          <Label className="label-caps">
            Max position · {(maxPositionPct * 100).toFixed(1)}% → cap {usd(cap)}
          </Label>
          <Slider
            className="mt-3"
            value={[maxPositionPct]}
            min={0}
            max={0.2}
            step={0.005}
            onValueChange={(values) => onMaxPositionPct(values[0] ?? maxPositionPct)}
          />
        </div>
        <label className="flex items-center gap-2">
          <Checkbox checked={pyramiding} onCheckedChange={(v) => onPyramiding(v === true)} />
          <span className="tape text-xs">
            Enable pyramiding <span className="text-muted-foreground">(scale into winners)</span>
          </span>
        </label>
      </div>
      <div className="overflow-x-auto border-t border-border">
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr className="label-caps border-b border-border text-left">
              <th className="px-4 py-2 font-normal">Market</th>
              <th className="font-normal">Current size</th>
              <th className="font-normal">Kelly suggestion</th>
              <th className="px-4 text-right font-normal">Delta</th>
            </tr>
          </thead>
          <tbody>
            {open.length ? (
              open.map((row) => {
                const price = row.price ?? 0.5;
                const suggestedRaw = kellySizeUsd({
                  winProb: Math.max(0.5, row.confidence),
                  price,
                  bankrollUsd: balance,
                  fractionOfKelly: kValue,
                  maxOrderUsd: Number.POSITIVE_INFINITY,
                });
                const suggested = Math.min(suggestedRaw, cap);
                const current = row.volume_usd;
                const delta = pyramiding ? suggested - current : Math.min(0, suggested - current);
                return (
                  <tr key={row.slug} className="border-b border-border/60 last:border-0">
                    <td className="max-w-[220px] truncate px-4 py-2" title={row.slug}>
                      {row.slug}
                    </td>
                    <td className="tape">{usd(current)}</td>
                    <td className="tape">{usd(suggested)}</td>
                    <td
                      className={`tape px-4 text-right ${delta >= 0 ? "text-up" : "text-down"}`}
                    >
                      {delta >= 0 ? "+" : "−"}
                      {usd(Math.abs(delta))}
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={4} className="tape px-4 py-6 text-center text-muted-foreground">
                  No open positions.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

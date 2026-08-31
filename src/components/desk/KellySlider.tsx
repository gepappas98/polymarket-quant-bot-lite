import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Panel, usd } from "@/components/dashboard/Panels";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { supabase } from "@/integrations/supabase/client";
import { kellyFraction, kellySizeUsd, winRateFromRecord, winProbFromEdge } from "@/lib/kelly";

export function KellySlider() {
  const [price, setPrice] = useState(0.52);
  const [edge, setEdge] = useState(0.04);
  const [bankroll, setBankroll] = useState(500);
  const [fraction, setFraction] = useState(0.5);
  const [maxOrder, setMaxOrder] = useState(50);
  const [override, setOverride] = useState<number | null>(null);
  const [useRecord, setUseRecord] = useState(false);
  const [strategy, setStrategy] = useState("market_making");

  const { data: record } = useQuery({
    queryKey: ["winrate"],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("historical_winrate")
        .select("strategy, wins, losses, avg_pnl");
      if (error) throw error;
      return data;
    },
  });

  const row = record?.find((r) => r.strategy === strategy);
  const winProb = useRecord && row ? winRateFromRecord(row.wins, row.losses) : winProbFromEdge(edge, price);
  const recommended = kellySizeUsd({
    winProb,
    price,
    bankrollUsd: bankroll,
    fractionOfKelly: fraction,
    maxOrderUsd: maxOrder,
  });

  return (
    <Panel title="Kelly sizing" hint="fractional kelly">
      <div className="grid gap-3 px-4 py-4 sm:grid-cols-2">
        <Field label="Outcome price" value={price} step={0.01} onChange={setPrice} />
        <Field label="Edge (fair − price)" value={edge} step={0.01} onChange={setEdge} />
        <Field label="Bankroll (USD)" value={bankroll} step={10} onChange={setBankroll} />
        <Field label="Max order (USD)" value={maxOrder} step={5} onChange={setMaxOrder} />
      </div>

      <div className="px-4 pb-4">
        <Label className="label-caps">Kelly fraction · {fraction.toFixed(2)}</Label>
        <Slider
          className="mt-3"
          value={[fraction]}
          min={0.1}
          max={1}
          step={0.05}
          onValueChange={(v) => setFraction(v[0] ?? 0.5)}
        />
      </div>

      <div className="flex items-center gap-2 px-4 pb-3">
        <input
          id="use-record"
          type="checkbox"
          checked={useRecord}
          onChange={(e) => setUseRecord(e.target.checked)}
        />
        <Label htmlFor="use-record" className="text-xs">
          Use historical win rate
        </Label>
        <select
          value={strategy}
          onChange={(e) => setStrategy(e.target.value)}
          className="ml-auto h-8 rounded-md border border-input bg-background px-2 text-xs"
        >
          {(record?.length ? record.map((r) => r.strategy) : ["market_making", "copy_trading"]).map(
            (s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ),
          )}
        </select>
      </div>

      <div className="grid grid-cols-3 gap-px border-t border-border bg-border">
        <Stat label="Win prob" value={`${(winProb * 100).toFixed(1)}%`} />
        <Stat label="Full Kelly f*" value={kellyFraction(winProb, price).toFixed(3)} />
        <Stat label="Recommended" value={usd(recommended)} />
      </div>

      <div className="flex items-end gap-2 px-4 py-4">
        <div className="flex-1 space-y-1.5">
          <Label className="label-caps" htmlFor="kelly-override">
            Manual override (USD)
          </Label>
          <Input
            id="kelly-override"
            type="number"
            value={override ?? ""}
            placeholder={String(recommended)}
            onChange={(e) => setOverride(e.target.value === "" ? null : Number(e.target.value))}
          />
        </div>
        <div className="pb-2">
          <div className="label-caps">Size used</div>
          <div className="tape text-sm">{usd(override ?? recommended)}</div>
        </div>
      </div>
    </Panel>
  );
}

function Field({
  label,
  value,
  step,
  onChange,
}: {
  label: string;
  value: number;
  step: number;
  onChange: (n: number) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="label-caps">{label}</Label>
      <Input type="number" step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card px-4 py-3">
      <div className="label-caps">{label}</div>
      <div className="tape mt-1 text-sm">{value}</div>
    </div>
  );
}

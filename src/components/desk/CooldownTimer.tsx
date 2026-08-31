import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { toast } from "sonner";
import { Panel } from "@/components/dashboard/Panels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getCooldown } from "@/lib/trading.functions";

export function CooldownTimer({ market = "BTC-MM" }: { market?: string }) {
  const fn = useServerFn(getCooldown);
  const [seconds, setSeconds] = useState(300);
  const [remaining, setRemaining] = useState(0);

  const { data, refetch } = useQuery({
    queryKey: ["cooldown", market],
    queryFn: () => fn({ data: { market, arm: false } }),
    refetchInterval: 30_000,
  });

  useEffect(() => {
    if (data) setRemaining(data.remainingSeconds);
  }, [data]);

  useEffect(() => {
    const id = setInterval(() => setRemaining((r) => Math.max(0, r - 1)), 1000);
    return () => clearInterval(id);
  }, []);

  const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
  const ss = String(remaining % 60).padStart(2, "0");

  return (
    <Panel title="Cooldown" hint={`${market} · persisted`}>
      <div className="px-4 py-4">
        <div className={`tape text-3xl font-medium ${remaining > 0 ? "text-warn" : "text-up"}`}>
          {mm}:{ss}
        </div>
        <p className="tape mt-1 text-[11px] text-muted-foreground">
          {remaining > 0 ? "Trading blocked for this market" : "Clear to trade"}
        </p>
        <div className="mt-4 flex items-end gap-2">
          <div className="flex-1 space-y-1.5">
            <Label className="label-caps" htmlFor="cd-secs">
              Cooldown seconds
            </Label>
            <Input
              id="cd-secs"
              type="number"
              min={0}
              value={seconds}
              onChange={(e) => setSeconds(Number(e.target.value))}
            />
          </div>
          <Button
            variant="outline"
            onClick={async () => {
              await fn({ data: { market, arm: true, cooldownSeconds: seconds } });
              toast.success("Cooldown armed");
              void refetch();
            }}
          >
            Arm now
          </Button>
        </div>
      </div>
    </Panel>
  );
}

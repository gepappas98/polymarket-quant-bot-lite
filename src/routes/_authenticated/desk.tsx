import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { supabase } from "@/integrations/supabase/client";
import { useSupabaseUser } from "@/hooks/useSupabaseUser";
import { Button } from "@/components/ui/button";
import { MarketMakingPanel } from "@/components/desk/MarketMakingPanel";
import { CopyTradingPanel } from "@/components/desk/CopyTradingPanel";
import { KellySlider } from "@/components/desk/KellySlider";
import { CooldownTimer } from "@/components/desk/CooldownTimer";
import { StrategyManager } from "@/components/desk/StrategyManager";
import { BacktestConfig } from "@/components/desk/BacktestConfig";
import { AlertConfigPanel } from "@/components/desk/AlertConfigPanel";
import { NavLinks } from "@/components/dashboard/NavLinks";

export const Route = createFileRoute("/_authenticated/desk")({
  head: () => ({
    meta: [
      { title: "Trading desk — Polymarket Quant Bot" },
      {
        name: "description",
        content:
          "Private trading desk: market-making quotes, copy-trading watchlist, Kelly sizing, persistent cooldowns, strategy plugins, backtests and alerts.",
      },
      { property: "og:title", content: "Trading desk — Polymarket Quant Bot" },
      {
        property: "og:description",
        content: "Market-making, copy-trading, Kelly sizing, cooldowns, backtests and alerting.",
      },
    ],
  }),
  component: Desk,
});

function Desk() {
  const { user } = useSupabaseUser();
  const navigate = useNavigate();

  return (
    <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-10">
      <header className="panel mb-6 flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-4">
        <div>
          <h1 className="text-lg font-bold tracking-tight sm:text-xl">Trading desk</h1>
          <p className="tape mt-1 text-[11px] text-muted-foreground">
            market making · copy trading · kelly sizing · cooldowns · backtests · alerts
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <NavLinks />
          <span className="tape rounded border border-border bg-muted px-2 py-1 text-[10px] text-muted-foreground">
            {user?.email ?? "signed in"}
          </span>
          <Link
            to="/"
            className="tape rounded border border-border px-2 py-1 text-[10px] uppercase"
          >
            monitor
          </Link>
          <Button
            size="sm"
            variant="outline"
            onClick={async () => {
              await supabase.auth.signOut();
              navigate({ to: "/auth" });
            }}
          >
            Sign out
          </Button>
        </div>
      </header>

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-2">
          <MarketMakingPanel />
          <CopyTradingPanel />
          <BacktestConfig />
        </div>
        <div className="space-y-3">
          <CooldownTimer />
          <KellySlider />
          <StrategyManager />
          <AlertConfigPanel />
        </div>
      </div>
    </main>
  );
}

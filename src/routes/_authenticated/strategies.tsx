import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { NavLinks } from "@/components/dashboard/NavLinks";
import { Panel } from "@/components/dashboard/Panels";
import { Switch } from "@/components/ui/switch";
import {
  getStrategies,
  riskQueryKeys,
  updateStrategies,
  type StrategiesResponse,
  type StrategyFlags,
} from "@/lib/riskApi";

export const Route = createFileRoute("/_authenticated/strategies")({
  head: () => ({
    meta: [
      { title: "Strategies — Polymarket Quant Bot" },
      { name: "description", content: "Configure the advanced risk engine strategy filters." },
    ],
  }),
  component: StrategiesPage,
});

const strategyCards: { key: keyof StrategyFlags; title: string; description: string }[] = [
  {
    key: "politics_only",
    title: "Politics only",
    description: "Ignore every market outside politics.",
  },
  {
    key: "sports_fade",
    title: "Sports fade",
    description: "Skip sports markets when evaluating new trades.",
  },
  {
    key: "crypto_focus",
    title: "Crypto focus",
    description: "Restrict new trades to crypto markets.",
  },
];

function StrategiesPage() {
  const queryClient = useQueryClient();
  const [optimistic, setOptimistic] = useState<StrategyFlags | null>(null);
  const strategies = useQuery({
    queryKey: riskQueryKeys.strategies(),
    queryFn: getStrategies,
  });
  const mutation = useMutation({
    mutationFn: (flags: StrategyFlags) => updateStrategies(flags),
    onMutate: async (flags) => {
      await queryClient.cancelQueries({ queryKey: riskQueryKeys.strategies() });
      const previous = queryClient.getQueryData<StrategiesResponse>(riskQueryKeys.strategies());
      setOptimistic(flags);
      queryClient.setQueryData<StrategiesResponse>(riskQueryKeys.strategies(), (current) => ({
        ...(current ?? { active: [], categories: [] }),
        ...flags,
        flags,
      }));
      return { previous };
    },
    onError: (error, _flags, context) => {
      if (context?.previous) queryClient.setQueryData(riskQueryKeys.strategies(), context.previous);
      setOptimistic(null);
      toast.error(error.message);
    },
    onSuccess: (next) => {
      queryClient.setQueryData(riskQueryKeys.strategies(), next);
      setOptimistic(null);
      toast.success("Strategy updated");
    },
  });
  const data = strategies.data;
  const flags = optimistic ??
    data ?? { politics_only: false, sports_fade: false, crypto_focus: false };

  function toggle(key: keyof StrategyFlags, checked: boolean) {
    const next = { ...flags, [key]: checked };
    setOptimistic(next);
    mutation.mutate(next);
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:py-10">
      <header className="panel mb-6 flex flex-wrap items-center gap-4 px-4 py-4">
        <div>
          <h1 className="text-lg font-bold tracking-tight sm:text-xl">Risk strategies</h1>
          <p className="tape mt-1 text-[11px] text-muted-foreground">
            market filters for the advanced risk engine
          </p>
        </div>
        <div className="ml-auto">
          <NavLinks />
        </div>
      </header>

      {strategies.isError ? <OfflineNotice /> : null}
      <div className="grid gap-3 md:grid-cols-3">
        {strategyCards.map((card) => (
          <div key={card.key} className="panel flex min-h-36 flex-col justify-between p-4">
            <div>
              <h2 className="font-medium">{card.title}</h2>
              <p className="tape mt-2 text-[11px] text-muted-foreground">{card.description}</p>
            </div>
            <div className="mt-5 flex items-center justify-between">
              <span className="label-caps">{flags[card.key] ? "enabled" : "disabled"}</span>
              <Switch
                checked={flags[card.key]}
                onCheckedChange={(checked) => toggle(card.key, checked)}
                disabled={mutation.isPending}
                aria-label={card.title}
              />
            </div>
          </div>
        ))}
      </div>

      <Panel title="Resulting allowed categories" hint="read-only">
        {data?.categories?.length ? (
          <div className="flex flex-wrap gap-2 px-4 py-4">
            {data.categories.map((category) => (
              <span
                key={category}
                className="tape rounded border border-up/40 bg-up/10 px-2 py-1 text-[11px] uppercase text-up"
              >
                {category}
              </span>
            ))}
          </div>
        ) : (
          <p className="px-4 py-4 tape text-[11px] text-muted-foreground">
            No category filters enabled; all categories are allowed.
          </p>
        )}
      </Panel>
    </main>
  );
}

function OfflineNotice() {
  return (
    <div className="mb-3 rounded-md border border-warn/40 bg-warn/10 px-4 py-3 tape text-[11px] text-warn">
      API offline — start <code>uvicorn app.main:app</code>
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { NavLinks } from "@/components/dashboard/NavLinks";
import { FeatureImportancePanel, VolatilityPanel } from "@/components/dashboard/AnalyticsPanels";
import { getMarketsSnapshot, analyticsQueryKeys } from "@/lib/riskApi";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useState } from "react";

export const Route = createFileRoute("/advanced")({
  head: () => ({ meta: [{ title: "Advanced analytics — Polymarket Quant Bot" }, { name: "description", content: "SHAP feature attribution, rolling volatility, and momentum analytics." }] }),
  component: AdvancedPage,
});

function AdvancedPage() {
  const markets = useQuery({ queryKey: analyticsQueryKeys.snapshot(), queryFn: () => getMarketsSnapshot(), staleTime: 30_000 });
  const [market, setMarket] = useState("");
  const selected = market || markets.data?.[0]?.slug || "";
  return <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-10"><header className="panel mb-6 flex flex-wrap items-center gap-4 px-4 py-4"><div><h1 className="text-lg font-bold tracking-tight sm:text-xl">Advanced analytics</h1><p className="tape mt-1 text-[11px] text-muted-foreground">model attribution · volatility · momentum</p></div><div className="ml-auto flex items-center gap-3"><NavLinks /><Select value={selected} onValueChange={setMarket}><SelectTrigger className="w-56"><SelectValue placeholder="Select market" /></SelectTrigger><SelectContent>{(markets.data ?? []).map((item) => <SelectItem key={item.slug} value={item.slug}>{item.slug}</SelectItem>)}</SelectContent></Select></div></header><div className="grid gap-3 lg:grid-cols-2"><FeatureImportancePanel /><VolatilityPanel marketSlug={selected} /></div></main>;
}

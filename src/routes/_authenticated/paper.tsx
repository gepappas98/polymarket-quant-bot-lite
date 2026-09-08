import { createFileRoute } from "@tanstack/react-router";
import { NavLinks } from "@/components/dashboard/NavLinks";
import { PaperDesk } from "@/components/paper/PaperDesk";

export const Route = createFileRoute("/_authenticated/paper")({
  head: () => ({
    meta: [
      { title: "Paper mode — Polymarket Quant Bot" },
      {
        name: "description",
        content: "Private paper-trading account with risk gates, positions, realized P&L and trade history.",
      },
    ],
  }),
  component: PaperPage,
});

function PaperPage() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-10">
      <header className="panel mb-6 flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-4">
        <div>
          <h1 className="text-lg font-bold tracking-tight sm:text-xl">Paper mode</h1>
          <p className="tape mt-1 text-[11px] text-muted-foreground">
            simulated execution · risk gates · positions · realized P&amp;L
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <NavLinks />
          <span className="tape rounded border border-warning/50 bg-warning/10 px-2 py-1 text-[10px] uppercase text-warning">
            paper only
          </span>
        </div>
      </header>
      <PaperDesk />
    </main>
  );
}

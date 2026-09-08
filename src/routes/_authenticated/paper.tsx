import { createFileRoute, Link, Outlet } from "@tanstack/react-router";
import { NavLinks } from "@/components/dashboard/NavLinks";

export const Route = createFileRoute("/_authenticated/paper")({
  head: () => ({
    meta: [
      { title: "Paper mode — Polymarket Quant Bot" },
      {
        name: "description",
        content: "Private paper-trading account with risk gates, positions, orders, history and reconciliation.",
      },
    ],
  }),
  component: PaperLayout,
});

const tabs = [
  ["desk", "/paper"],
  ["orders", "/paper/orders"],
  ["history", "/paper/history"],
  ["reconcile", "/paper/reconcile"],
] as const;

function PaperLayout() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-10">
      <header className="panel mb-6 flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-4">
        <div>
          <h1 className="text-lg font-bold tracking-tight sm:text-xl">Paper mode</h1>
          <p className="tape mt-1 text-[11px] text-muted-foreground">
            simulated execution · risk gates · orders · history · reconcile
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <NavLinks />
          <span className="tape rounded border border-warning/50 bg-warning/10 px-2 py-1 text-[10px] uppercase text-warning">
            paper only
          </span>
        </div>
      </header>

      <nav className="mb-4 flex flex-wrap gap-1" aria-label="Paper sections">
        {tabs.map(([label, to]) => (
          <Link
            key={to}
            to={to}
            activeOptions={{ exact: true }}
            activeProps={{ className: "border-primary/50 bg-primary/15 text-primary" }}
            className="tape rounded border border-border px-2 py-1 text-[10px] uppercase text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            {label}
          </Link>
        ))}
      </nav>

      <Outlet />
    </main>
  );
}

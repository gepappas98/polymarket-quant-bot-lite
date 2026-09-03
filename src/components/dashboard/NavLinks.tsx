import { Link } from "@tanstack/react-router";

const links = [
  ["monitor", "/"],
  ["desk", "/desk"],
  ["leaders", "/leaders"],
  ["advanced", "/advanced"],
  ["sizing", "/sizing"],
  ["strategies", "/strategies"],
  ["settings", "/settings"],
] as const;

export function NavLinks() {
  return (
    <nav className="flex flex-wrap items-center gap-1" aria-label="Primary navigation">
      {links.map(([label, to]) => (
        <Link
          key={to}
          to={to}
          activeProps={{ className: "border-primary/50 bg-primary/15 text-primary" }}
          className="tape rounded border border-border px-2 py-1 text-[10px] uppercase text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}

import { useQuery } from "@tanstack/react-query";
import { getPolymarketConfiguration } from "@/lib/polymarket.functions";

export function PolymarketStatus() {
  const query = useQuery({
    queryKey: ["polymarket", "configuration"],
    queryFn: () => getPolymarketConfiguration(),
  });

  if (query.isLoading)
    return (
      <div className="panel px-4 py-4 text-sm text-muted-foreground">
        Checking Polymarket API connectivity…
      </div>
    );
  if (query.isError)
    return (
      <div className="panel border-down/40 bg-down/5 px-4 py-4 text-sm text-down">
        Polymarket API unavailable: {query.error.message}
      </div>
    );

  if (!query.data) return null;
  const { config, capabilities } = query.data;
  return (
    <section className="panel px-4 py-4" aria-labelledby="polymarket-connectivity-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="polymarket-connectivity-title" className="text-sm font-semibold">
            Polymarket API connectivity
          </h2>
          <p className="tape mt-1 text-[11px] text-muted-foreground">
            Gamma · CLOB · Data · WebSocket · Relayer · Bridge
          </p>
        </div>
        <span className="tape rounded border border-up/40 bg-up/10 px-2 py-1 text-[10px] uppercase text-up">
          paper ready
        </span>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        {capabilities.map((capability) => (
          <div
            key={capability.name}
            className="rounded border border-border/70 bg-muted/20 px-3 py-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="label-caps text-[10px]">{capability.name}</span>
              <span
                className={
                  capability.enabled
                    ? "text-up"
                    : capability.configured
                      ? "text-warning"
                      : "text-muted-foreground"
                }
              >
                {capability.enabled
                  ? "ready"
                  : capability.configured
                    ? "read-only"
                    : "not configured"}
              </span>
            </div>
            <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
              {capability.reason}
            </p>
          </div>
        ))}
      </div>
      <div className="mt-3 grid gap-2 text-[11px] text-muted-foreground sm:grid-cols-4">
        <span>Gamma: {new URL(config.gammaBaseUrl).hostname}</span>
        <span>CLOB: {new URL(config.clobBaseUrl).hostname}</span>
        <span>Data: {new URL(config.dataBaseUrl).hostname}</span>
        <span>WebSocket: {new URL(config.wsUrl).hostname}</span>
      </div>
    </section>
  );
}

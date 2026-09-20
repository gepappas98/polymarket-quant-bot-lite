import { createFileRoute } from "@tanstack/react-router";
import { fetchWorkerPortfolio } from "@/lib/worker.server";

/**
 * Real balance / equity / open-position figures derived from the Render worker.
 * Worker URL and token stay server-side; no demo values are ever returned.
 */
export const Route = createFileRoute("/api/public/worker-metrics")({
  server: {
    handlers: {
      GET: async () => {
        try {
          const portfolio = await fetchWorkerPortfolio();
          return Response.json(portfolio, { headers: { "Cache-Control": "no-store" } });
        } catch (error) {
          const detail = error instanceof Error ? error.message : "worker metrics unavailable";
          return Response.json(
            { error: "REAL worker metrics unavailable", detail },
            { status: 503, headers: { "Cache-Control": "no-store" } },
          );
        }
      },
    },
  },
});

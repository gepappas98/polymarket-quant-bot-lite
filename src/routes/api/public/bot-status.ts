import { createFileRoute } from "@tanstack/react-router";

/**
 * Raw HTTP status endpoint for the Control Room.
 *
 * The dashboard reads this instead of a server function: server-fn calls resolve
 * through a build-time id manifest, and a stale/mismatched published bundle makes
 * the RPC fail with "Server function info not found" — a transport-level 500 that
 * no handler-level try/catch can intercept. A server route has a stable URL and
 * always reaches the handler, so the demo fallback can actually do its job.
 *
 * Read-only, public worker status only. No secrets are returned.
 */
export const Route = createFileRoute("/api/public/bot-status")({
  server: {
    handlers: {
      GET: async () => {
        const { fetchWorkerStatus, buildDemoStatus } = await import("@/lib/bot.server");
        try {
          const status = await fetchWorkerStatus();
          return Response.json(status, {
            headers: { "cache-control": "no-store" },
          });
        } catch (err) {
          const demo = buildDemoStatus();
          demo.status_error = err instanceof Error ? err.message : "worker status unavailable";
          return Response.json(demo, { headers: { "cache-control": "no-store" } });
        }
      },
    },
  },
});

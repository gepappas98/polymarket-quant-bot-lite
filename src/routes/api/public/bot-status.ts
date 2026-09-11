import { createFileRoute } from "@tanstack/react-router";
import { fetchLiveWorkerStatus } from "@/lib/bot.server";

/**
 * Public dashboard status proxy. The worker URL and API token remain server-side;
 * this endpoint never returns the local demo status.
 */
export const Route = createFileRoute("/api/public/bot-status")({
  server: {
    handlers: {
      GET: async () => {
        try {
          const status = await fetchLiveWorkerStatus();
          return Response.json(status, {
            headers: { "Cache-Control": "no-store" },
          });
        } catch (error) {
          const message = error instanceof Error ? error.message : "worker status unavailable";
          return Response.json(
            { error: "REAL worker status unavailable", detail: message },
            { status: 503, headers: { "Cache-Control": "no-store" } },
          );
        }
      },
    },
  },
});

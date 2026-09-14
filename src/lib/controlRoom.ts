import type { QueryClient } from "@tanstack/react-query";

/**
 * Refresh every Control Room data source after a trade so worker-derived
 * stats (status, risk gates, metrics, market snapshot) update immediately
 * instead of waiting for the next poll.
 */
export function invalidateControlRoom(qc: QueryClient): void {
  qc.invalidateQueries({ queryKey: ["bot-status"] });
  qc.invalidateQueries({ queryKey: ["risk-api"] });
}

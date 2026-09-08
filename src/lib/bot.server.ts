import type { BotStatus } from "./bot-types";
import { buildDemoStatus } from "./bot-demo";

export { buildDemoStatus };

export function configuredAppMode(): "DEMO" | "PRODUCTION" {
  const mode = process.env["APP_MODE"]?.trim().toUpperCase() || "PRODUCTION";
  if (mode !== "DEMO" && mode !== "PRODUCTION") {
    throw new Error(`invalid APP_MODE=${mode}; expected DEMO or PRODUCTION`);
  }
  return mode;
}

/** Fetch status from a running worker, or an explicitly configured demo feed. */
export async function fetchWorkerStatus(): Promise<BotStatus> {
  if (configuredAppMode() === "DEMO") return buildDemoStatus();
  const url = process.env["BOT_STATUS_URL"];
  if (!url) throw new Error("REAL worker status unavailable: BOT_STATUS_URL is not configured");
  const token = process.env["BOT_STATUS_API_TOKEN"];
  const res = await fetch(url, {
    headers: {
      accept: "application/json",
      ...(token ? { "X-API-Token": token } : {}),
    },
  });
  if (!res.ok) throw new Error(`worker status unavailable (${res.status})`);
  const data = (await res.json()) as Partial<BotStatus>;
  if (
    data.source !== "worker" ||
    data.data_source !== "REAL" ||
    data.market_data_source !== "REAL" ||
    typeof data.is_simulated !== "boolean"
  ) {
    throw new Error("worker status rejected: missing or invalid REAL/PAPER boundary metadata");
  }
  return data as BotStatus;
}

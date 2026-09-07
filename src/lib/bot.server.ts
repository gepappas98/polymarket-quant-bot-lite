import type { BotStatus } from "./bot-types";
import { buildDemoStatus } from "./bot-demo";

export { buildDemoStatus };

/** Fetch status from a running worker, if one is configured. */
export async function fetchWorkerStatus(): Promise<BotStatus> {
  const url = process.env["BOT_STATUS_URL"];
  if (!url) return buildDemoStatus();
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

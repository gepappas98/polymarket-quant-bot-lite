import type { BotStatus } from "./bot-types";
import { buildDemoStatus } from "./bot-demo";
import { adaptWorkerRiskStatus, isWorkerRiskStatus } from "./bot-adapter";

export { buildDemoStatus };

/** Public sidecar status endpoint; overridable with BOT_STATUS_URL. */
const DEFAULT_STATUS_URL = "https://polymarket-quant-bot-lite-1.onrender.com/api/status";

function statusUrl(): string | undefined {
  return process.env["BOT_STATUS_URL"] ?? DEFAULT_STATUS_URL;
}

async function fetchConfiguredWorkerStatus(): Promise<BotStatus> {
  const url = statusUrl();
  if (!url) throw new Error("live worker status is not configured: BOT_STATUS_URL is missing");
  const token = process.env["BOT_STATUS_API_TOKEN"];
  const res = await fetch(url, {
    headers: {
      accept: "application/json",
      ...(token ? { "X-API-Token": token, authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!res.ok) throw new Error(`worker status unavailable (${res.status})`);
  const data = (await res.json()) as unknown;

  // Sidecar risk status → translate into the dashboard shape.
  if (isWorkerRiskStatus(data)) return adaptWorkerRiskStatus(data);

  const full = data as Partial<BotStatus>;
  if (
    full.source !== "worker" ||
    full.data_source !== "REAL" ||
    full.market_data_source !== "REAL" ||
    typeof full.is_simulated !== "boolean"
  ) {
    throw new Error("worker status rejected: missing or invalid REAL/PAPER boundary metadata");
  }
  return full as BotStatus;
}


/** Fetch status from a running worker; fall back to demo when missing or unreachable. */
export async function fetchWorkerStatus(): Promise<BotStatus> {
  if (!process.env["BOT_STATUS_URL"]) return buildDemoStatus();
  try {
    return await fetchConfiguredWorkerStatus();
  } catch (err) {
    const demo = buildDemoStatus();
    demo.status_error = err instanceof Error ? err.message : "worker status unavailable";
    return demo;
  }
}

/** Strict live status for production Paper Desk market prices; never returns demo data. */
export async function fetchLiveWorkerStatus(): Promise<BotStatus> {
  return fetchConfiguredWorkerStatus();
}

import type { BotStatus } from "./bot-types";
import { buildDemoStatus } from "./bot-demo";

export { buildDemoStatus };

/** Fetch status from a running worker, if one is configured. */
export async function fetchWorkerStatus(): Promise<BotStatus> {
  const url = process.env["BOT_STATUS_URL"];
  if (!url) return buildDemoStatus();
  try {
    const token = process.env["BOT_STATUS_API_TOKEN"];
    const res = await fetch(url, {
      headers: {
        accept: "application/json",
        ...(token ? { "X-API-Token": token } : {}),
      },
    });
    if (!res.ok) throw new Error(`worker responded ${res.status}`);
    const data = (await res.json()) as Partial<BotStatus>;
    const demo = buildDemoStatus();
    return { ...demo, ...data, source: "worker", swarm: data.swarm ?? demo.swarm ?? null };
  } catch {
    return buildDemoStatus();
  }
}

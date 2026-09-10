import { createServerFn } from "@tanstack/react-start";
import type { BotStatus } from "./bot-types";
import { buildDemoStatus, fetchWorkerStatus } from "./bot.server";

export const getBotStatus = createServerFn({ method: "GET" }).handler(
  async (): Promise<BotStatus> => {
    try {
      return await fetchWorkerStatus();
    } catch (err) {
      // Never fail the request: the dashboard renders read-only demo data instead of a 500.
      const demo = buildDemoStatus();
      demo.status_error = err instanceof Error ? err.message : "worker status unavailable";
      return demo;
    }
  },
);

import { createServerFn } from "@tanstack/react-start";
import type { BotStatus } from "./bot-types";
import { fetchWorkerStatus } from "./bot.server";

export const getBotStatus = createServerFn({ method: "GET" }).handler(
  async (): Promise<BotStatus> => fetchWorkerStatus(),
);

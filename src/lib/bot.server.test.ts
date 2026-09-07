import { afterEach, describe, expect, it, vi } from "vitest";
import { buildDemoStatus } from "./bot-demo";
import { fetchWorkerStatus } from "./bot.server";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("REAL/PAPER/DEMO boundary", () => {
  it("classifies browser-generated values as DEMO, never LIVE", () => {
    const status = buildDemoStatus(1_700_000_000_000);
    expect(status.data_source).toBe("DEMO");
    expect(status.market_data_source).toBe("DEMO");
    expect(status.execution_mode).toBe("DEMO");
    expect(status.is_simulated).toBe(true);
    expect(status.liveTradingAllowed).toBe(false);
  });

  it("rejects a worker response without REAL market-data metadata", async () => {
    vi.stubEnv("BOT_STATUS_URL", "https://worker.example/status");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ source: "worker" }), { status: 200 })),
    );
    await expect(fetchWorkerStatus()).rejects.toThrow("boundary metadata");
  });

  it("does not convert worker outages into DEMO status", async () => {
    vi.stubEnv("BOT_STATUS_URL", "https://worker.example/status");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("offline", { status: 503 })),
    );
    await expect(fetchWorkerStatus()).rejects.toThrow("worker status unavailable");
  });

  it("keeps fake clients in test code rather than production modules", async () => {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const production = [path.resolve(process.cwd(), "bot"), path.resolve(process.cwd(), "src")];
    for (const root of production) {
      const files = await fs.readdir(root, { recursive: true });
      for (const file of files.filter(
        (name) => name.endsWith(".py") || name.endsWith(".ts") || name.endsWith(".tsx"),
      )) {
        const full = path.join(root, file);
        if (full.endsWith(".test.ts") || full.endsWith(".test.tsx")) continue;
        const source = await fs.readFile(full, "utf8");
        expect(source).not.toMatch(/class\s+Fake(?:Book|Client|Response)\b/);
      }
    }
  });
});

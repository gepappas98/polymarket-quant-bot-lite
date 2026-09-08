import { describe, expect, it } from "vitest";
import { decideCopy, dedupeActivity, normalizeTraderActivity } from "./copyActivity";

const wallet = "0x0000000000000000000000000000000000000001";
const raw = (overrides: Record<string, unknown> = {}) => ({
  id: "activity-1",
  conditionId: "market-1",
  asset: "token-1",
  slug: "market-slug",
  side: "BUY",
  price: "0.42",
  size: "10",
  usdcSize: "4.2",
  timestamp: "1700000000",
  ...overrides,
});

function observed(overrides: Record<string, unknown> = {}) {
  return normalizeTraderActivity(raw(overrides), wallet, 1_700_000_100_000)!;
}

describe("verified copy activity", () => {
  it("deduplicates the same trader event", () => {
    expect(dedupeActivity([observed(), observed()])).toHaveLength(1);
  });

  it("rejects missing markets and invalid quantities", () => {
    expect(normalizeTraderActivity(raw({ conditionId: "", asset: "" }), wallet, 1_700_000_100_000)).toBeNull();
    expect(decideCopy(observed({ size: "0" }), 1_700_000_100_000).reason).toBe("INVALID_QUANTITY");
  });

  it("rejects stale events", () => {
    expect(decideCopy(observed(), 1_700_001_000_000).reason).toBe("STALE_EVENT");
  });

  it("accepts a real event only as PAPER and rejects risk or live execution", () => {
    expect(decideCopy(observed(), 1_700_000_100_000)).toMatchObject({ status: "ACCEPTED", mode: "PAPER" });
    expect(decideCopy(observed({ usdcSize: "1000" }), 1_700_000_100_000).reason).toBe("RISK_REJECTED");
    expect(decideCopy(observed(), 1_700_000_100_000, { live: true }).reason).toBe("LIVE_COPY_DISABLED");
  });
});

import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";
import { normalizeTraderActivity, dedupeActivity, type ObservedTraderActivity } from "./copyActivity";

export type WalletActivityResponse = { ok: boolean; reason?: string; activity: ObservedTraderActivity[] };

const walletSchema = z.string().regex(/^0x[a-fA-F0-9]{40}$/);

export const fetchWalletActivity = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) => z.object({ wallet: walletSchema, limit: z.number().int().min(1).max(100).default(50) }).parse(input))
  .handler(async ({ data }): Promise<WalletActivityResponse> => {
    try {
      const res = await fetch(
        `https://data-api.polymarket.com/activity?user=${encodeURIComponent(data.wallet)}&limit=${data.limit}`,
        { headers: { Accept: "application/json" }, cache: "no-store" },
      );
      if (!res.ok) return { ok: false, reason: `polymarket ${res.status}`, activity: [] };
      const payload = (await res.json()) as unknown;
      const rows = Array.isArray(payload) ? payload : payload && typeof payload === "object" && Array.isArray((payload as { data?: unknown }).data) ? (payload as { data: unknown[] }).data : [];
      const activity = dedupeActivity(rows.map((row) => normalizeTraderActivity(row, data.wallet)).filter((row): row is ObservedTraderActivity => row !== null));
      return activity.length ? { ok: true, activity } : { ok: false, reason: "no verified Polymarket activity", activity: [] };
    } catch {
      return { ok: false, reason: "polymarket activity unavailable", activity: [] };
    }
  });

/** Kept for read-only position reconciliation; positions are not copy-trade events. */
export interface WalletPosition {
  market: string;
  outcome: string;
  size: number;
  avgPrice: number;
  currentValue: number;
  pnl: number;
}

export const fetchWalletPositions = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) => z.object({ wallet: walletSchema }).parse(input))
  .handler(async ({ data }): Promise<{ ok: boolean; reason?: string; positions: WalletPosition[] }> => {
    try {
      const res = await fetch(`https://data-api.polymarket.com/positions?user=${encodeURIComponent(data.wallet)}&sizeThreshold=1&limit=50`, { headers: { Accept: "application/json" }, cache: "no-store" });
      if (!res.ok) return { ok: false, reason: `polymarket ${res.status}`, positions: [] };
      const rows = (await res.json()) as Array<Record<string, unknown>>;
      if (!Array.isArray(rows)) return { ok: false, reason: "invalid Polymarket positions response", positions: [] };
      return {
        ok: true,
        positions: rows.map((row) => ({
          market: String(row["title"] ?? row["slug"] ?? "unknown"),
          outcome: String(row["outcome"] ?? "-"),
          size: Number(row["size"] ?? 0),
          avgPrice: Number(row["avgPrice"] ?? 0),
          currentValue: Number(row["currentValue"] ?? 0),
          pnl: Number(row["cashPnl"] ?? 0),
        })).filter((position) => Number.isFinite(position.size) && position.size > 0),
      };
    } catch {
      return { ok: false, reason: "polymarket positions unavailable", positions: [] };
    }
  });

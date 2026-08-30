import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";

export interface WalletPosition {
  market: string;
  outcome: string;
  size: number;
  avgPrice: number;
  currentValue: number;
  pnl: number;
}

/** Read a wallet's open Polymarket positions (server-side to dodge CORS). */
export const fetchWalletPositions = createServerFn({ method: "POST" })
  .inputValidator((input) =>
    z.object({ wallet: z.string().regex(/^0x[a-fA-F0-9]{40}$/) }).parse(input),
  )
  .handler(async ({ data }): Promise<{ ok: boolean; reason?: string; positions: WalletPosition[] }> => {
    try {
      const res = await fetch(
        `https://data-api.polymarket.com/positions?user=${data.wallet}&sizeThreshold=1&limit=50`,
      );
      if (!res.ok) return { ok: false, reason: `polymarket ${res.status}`, positions: [] };
      const rows = (await res.json()) as Array<{
        title?: string;
        slug?: string;
        outcome?: string;
        size?: number;
        avgPrice?: number;
        currentValue?: number;
        cashPnl?: number;
      }>;
      return {
        ok: true,
        positions: rows.map((r) => ({
          market: r.title ?? r.slug ?? "unknown",
          outcome: r.outcome ?? "-",
          size: Number(r.size ?? 0),
          avgPrice: Number(r.avgPrice ?? 0),
          currentValue: Number(r.currentValue ?? 0),
          pnl: Number(r.cashPnl ?? 0),
        })),
      };
    } catch {
      return { ok: false, reason: "polymarket unreachable", positions: [] };
    }
  });

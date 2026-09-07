import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";
import {
  getLiveCapabilities,
  getPolymarketActivity,
  getPolymarketBook,
  getPolymarketConfig,
  getPolymarketPositions,
  getPolymarketTrades,
  searchPolymarketMarkets,
} from "./polymarket.server";

export const getPolymarketConfiguration = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(() => ({ config: getPolymarketConfig(), capabilities: getLiveCapabilities() }));

export const searchMarkets = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) =>
    z
      .object({ query: z.string().optional(), limit: z.number().int().min(1).max(100).default(25) })
      .parse(input),
  )
  .handler(({ data }) => searchPolymarketMarkets(data.query, data.limit));

export const getOrderBook = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) =>
    z.object({ tokenId: z.string().min(1), market: z.string().optional() }).parse(input),
  )
  .handler(({ data }) => getPolymarketBook(data.tokenId, data.market));

export const getMarketActivity = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) =>
    z
      .object({ address: z.string().min(1), limit: z.number().int().min(1).max(500).default(100) })
      .parse(input),
  )
  .handler(({ data }) => getPolymarketActivity(data.address, data.limit));

export const getMarketPositions = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) => z.object({ address: z.string().min(1) }).parse(input))
  .handler(({ data }) => getPolymarketPositions(data.address));

export const getMarketTrades = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) =>
    z
      .object({ address: z.string().min(1), limit: z.number().int().min(1).max(500).default(100) })
      .parse(input),
  )
  .handler(({ data }) => getPolymarketTrades(data.address, data.limit));

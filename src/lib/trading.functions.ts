import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";

/** get_mm_stats — P&L, inventory and spread stats from mm_trades. */
export const getMmStats = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) =>
    z
      .object({
        market: z.string().optional(),
        timeframeHours: z.number().min(1).max(24 * 30).default(24),
      })
      .parse(input ?? {}),
  )
  .handler(async ({ data, context }) => {
    const since = new Date(Date.now() - data.timeframeHours * 3_600_000).toISOString();
    let query = context.supabase
      .from("mm_trades")
      .select("market, side, price, size, pnl, timestamp")
      .gte("timestamp", since)
      .order("timestamp", { ascending: true });
    if (data.market) query = query.eq("market", data.market);

    const { data: rows, error } = await query;
    if (error) throw new Error(error.message);

    let inventory = 0;
    let notional = 0;
    let totalPnl = 0;
    let wins = 0;
    const equityCurve: { ts: string; pnl: number }[] = [];

    for (const r of rows ?? []) {
      const size = Number(r.size);
      const price = Number(r.price);
      inventory += r.side === "BUY" ? size : -size;
      notional += size * price;
      totalPnl += Number(r.pnl);
      if (Number(r.pnl) > 0) wins += 1;
      equityCurve.push({ ts: r.timestamp, pnl: Math.round(totalPnl * 100) / 100 });
    }

    const trades = rows?.length ?? 0;
    return {
      trades,
      inventory: Math.round(inventory * 10000) / 10000,
      notionalUsd: Math.round(notional * 100) / 100,
      totalPnl: Math.round(totalPnl * 100) / 100,
      winRatePct: trades ? Math.round((1000 * wins) / trades) / 10 : 0,
      equityCurve,
    };
  });

/** log_trade — idempotent-ish insert into mm_trades or copy_trades. */
export const logTrade = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) =>
    z
      .object({
        table: z.enum(["mm_trades", "copy_trades"]),
        market: z.string().min(1),
        side: z.string().min(1),
        price: z.number().nonnegative().optional(),
        size: z.number().positive(),
        pnl: z.number().default(0),
        wallet: z.string().optional(),
        strategy: z.string().optional(),
        status: z.enum(["pending", "mirrored", "skipped", "closed"]).optional(),
      })
      .parse(input),
  )
  .handler(async ({ data, context }) => {
    const { supabase, userId } = context;

    if (data.table === "mm_trades") {
      const side = data.side.toUpperCase() === "SELL" ? "SELL" : "BUY";
      const { data: row, error } = await supabase
        .from("mm_trades")
        .insert({
          user_id: userId,
          market: data.market,
          side,
          price: data.price ?? 0,
          size: data.size,
          pnl: data.pnl,
          strategy: data.strategy ?? null,
        })
        .select("id")
        .single();
      if (error) throw new Error(error.message);
      return { id: row.id };
    }

    const { data: row, error } = await supabase
      .from("copy_trades")
      .insert({
        user_id: userId,
        wallet: data.wallet ?? "unknown",
        market: data.market,
        side: data.side,
        size: data.size,
        price: data.price ?? null,
        pnl: data.pnl,
        status: data.status ?? "pending",
      })
      .select("id")
      .single();
    if (error) throw new Error(error.message);
    return { id: row.id };
  });

/** get_cooldown — read remaining seconds; optionally arm the cooldown now. */
export const getCooldown = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) =>
    z
      .object({
        market: z.string().min(1),
        arm: z.boolean().default(false),
        cooldownSeconds: z.number().int().min(0).max(86_400).default(300),
      })
      .parse(input),
  )
  .handler(async ({ data, context }) => {
    const { supabase, userId } = context;

    if (data.arm) {
      const { error } = await supabase.from("cooldown_state").upsert(
        {
          user_id: userId,
          market: data.market,
          last_trade_timestamp: new Date().toISOString(),
          cooldown_seconds: data.cooldownSeconds,
        },
        { onConflict: "user_id,market" },
      );
      if (error) throw new Error(error.message);
      return {
        market: data.market,
        remainingSeconds: data.cooldownSeconds,
        cooldownSeconds: data.cooldownSeconds,
      };
    }

    const { data: row, error } = await supabase
      .from("cooldown_state")
      .select("last_trade_timestamp, cooldown_seconds")
      .eq("market", data.market)
      .maybeSingle();
    if (error) throw new Error(error.message);
    if (!row) return { market: data.market, remainingSeconds: 0, cooldownSeconds: 0 };

    const elapsed = (Date.now() - new Date(row.last_trade_timestamp).getTime()) / 1000;
    return {
      market: data.market,
      remainingSeconds: Math.max(0, Math.round(row.cooldown_seconds - elapsed)),
      cooldownSeconds: row.cooldown_seconds,
    };
  });

/** send_alert — deliver via the configured channel and record it in alert_history. */
export const sendAlert = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) =>
    z
      .object({ configId: z.string().uuid().optional(), message: z.string().min(1).max(2000) })
      .parse(input),
  )
  .handler(async ({ data, context }) => {
    const { supabase, userId } = context;

    let channel = "email";
    let destination: string | null = null;
    if (data.configId) {
      const { data: cfg } = await supabase
        .from("alert_config")
        .select("channel, destination")
        .eq("id", data.configId)
        .maybeSingle();
      if (cfg) {
        channel = cfg.channel;
        destination = cfg.destination;
      }
    }

    let delivered = false;
    let deliveryError: string | null = null;
    try {
      if ((channel === "slack" || channel === "telegram") && destination) {
        const body =
          channel === "slack" ? { text: data.message } : { text: data.message, parse_mode: "HTML" };
        const res = await fetch(destination, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        });
        delivered = res.ok;
        if (!res.ok) deliveryError = `webhook responded ${res.status}`;
      } else {
        deliveryError = "no webhook destination configured — alert recorded only";
      }
    } catch {
      deliveryError = "webhook request failed";
    }

    const { error } = await supabase.from("alert_history").insert({
      user_id: userId,
      config_id: data.configId ?? null,
      message: delivered ? data.message : `${data.message} [${deliveryError}]`,
    });
    if (error) throw new Error(error.message);

    return { delivered, channel, error: deliveryError };
  });

/** fetch_kalshi — optional cross-venue reference price. */
export const fetchKalshi = createServerFn({ method: "POST" })
  .inputValidator((input) => z.object({ contract: z.string().min(1).max(64) }).parse(input))
  .handler(async ({ data }) => {
    try {
      const res = await fetch(
        `https://api.elections.kalshi.com/trade-api/v2/markets/${encodeURIComponent(data.contract)}`,
      );
      if (!res.ok) return { available: false as const, reason: `kalshi ${res.status}` };
      const json = (await res.json()) as {
        market?: { ticker?: string; yes_bid?: number; yes_ask?: number; last_price?: number };
      };
      const m = json.market;
      if (!m) return { available: false as const, reason: "contract not found" };
      return {
        available: true as const,
        ticker: m.ticker ?? data.contract,
        yesBid: (m.yes_bid ?? 0) / 100,
        yesAsk: (m.yes_ask ?? 0) / 100,
        last: (m.last_price ?? 0) / 100,
      };
    } catch {
      return { available: false as const, reason: "kalshi unreachable" };
    }
  });

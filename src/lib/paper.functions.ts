import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";

export interface PaperGate {
  name: string;
  allowed: boolean;
  reason: string;
}

const DEFAULT_BANKROLL = 10_000;

type Ctx = { supabase: any; userId: string };

async function loadAccount(ctx: Ctx) {
  const { data: existing, error } = await ctx.supabase
    .from("paper_accounts")
    .select("*")
    .eq("user_id", ctx.userId)
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (existing) return existing;
  const { data: created, error: insertError } = await ctx.supabase
    .from("paper_accounts")
    .insert({ user_id: ctx.userId, starting_bankroll: DEFAULT_BANKROLL, cash: DEFAULT_BANKROLL })
    .select("*")
    .single();
  if (insertError) throw new Error(insertError.message);
  return created;
}

async function todayRealized(ctx: Ctx) {
  const start = new Date();
  start.setUTCHours(0, 0, 0, 0);
  const { data, error } = await ctx.supabase
    .from("paper_trades")
    .select("realized_pnl")
    .eq("user_id", ctx.userId)
    .gte("created_at", start.toISOString());
  if (error) throw new Error(error.message);
  return (data ?? []).reduce((sum: number, r: { realized_pnl: number }) => sum + Number(r.realized_pnl), 0);
}

async function evaluateGates(
  ctx: Ctx,
  account: any,
  market: string,
  sizeUsd: number,
): Promise<PaperGate[]> {
  const dailyPnl = await todayRealized(ctx);
  const { data: positions } = await ctx.supabase
    .from("paper_positions")
    .select("cost_usd")
    .eq("user_id", ctx.userId);
  const openCost = (positions ?? []).reduce(
    (s: number, p: { cost_usd: number }) => s + Number(p.cost_usd),
    0,
  );
  const equity = Number(account.cash) + openCost;
  const maxPosition = (equity * Number(account.max_position_pct)) / 100;

  const { data: lastTrade } = await ctx.supabase
    .from("paper_trades")
    .select("created_at")
    .eq("user_id", ctx.userId)
    .eq("market", market)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  const cooldownSeconds = Number(account.cooldown_seconds);
  const elapsed = lastTrade
    ? (Date.now() - new Date(lastTrade.created_at).getTime()) / 1000
    : Number.POSITIVE_INFINITY;
  const cooldownLeft = Math.max(0, Math.round(cooldownSeconds - elapsed));

  return [
    {
      name: "bankroll",
      allowed: sizeUsd <= Number(account.cash) + 1e-9,
      reason: `cash $${Number(account.cash).toFixed(2)} vs order $${sizeUsd.toFixed(2)}`,
    },
    {
      name: "max_position",
      allowed: sizeUsd <= maxPosition + 1e-9,
      reason: `limit $${maxPosition.toFixed(2)} (${account.max_position_pct}% of $${equity.toFixed(2)})`,
    },
    {
      name: "daily_loss_limit",
      allowed: dailyPnl > -Number(account.daily_loss_limit),
      reason: `today ${dailyPnl >= 0 ? "+" : ""}$${dailyPnl.toFixed(2)} / limit -$${Number(account.daily_loss_limit).toFixed(2)}`,
    },
    {
      name: "cooldown",
      allowed: cooldownLeft <= 0,
      reason: cooldownLeft > 0 ? `${cooldownLeft}s remaining on ${market}` : "clear",
    },
  ];
}

/** Full paper-engine snapshot: account, open positions, realized P&L and trade ledger. */
export const getPaperState = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    const ctx = context as unknown as Ctx;
    const account = await loadAccount(ctx);
    const [{ data: positions }, { data: trades }] = await Promise.all([
      ctx.supabase
        .from("paper_positions")
        .select("*")
        .eq("user_id", ctx.userId)
        .order("opened_at", { ascending: false }),
      ctx.supabase
        .from("paper_trades")
        .select("*")
        .eq("user_id", ctx.userId)
        .order("created_at", { ascending: false })
        .limit(100),
    ]);
    const dailyPnl = await todayRealized(ctx);
    return {
      engine: "paper" as const,
      account: {
        startingBankroll: Number(account.starting_bankroll),
        cash: Number(account.cash),
        realizedPnl: Number(account.realized_pnl),
        dailyPnl: Math.round(dailyPnl * 100) / 100,
        dailyLossLimit: Number(account.daily_loss_limit),
        maxPositionPct: Number(account.max_position_pct),
        cooldownSeconds: Number(account.cooldown_seconds),
      },
      positions: (positions ?? []).map((p: any) => ({
        id: p.id as string,
        market: p.market as string,
        side: p.side as "UP" | "DOWN",
        shares: Number(p.shares),
        avgPrice: Number(p.avg_price),
        costUsd: Number(p.cost_usd),
        openedAt: p.opened_at as string,
      })),
      trades: (trades ?? []).map((t: any) => ({
        id: t.id as string,
        market: t.market as string,
        side: t.side as string,
        action: t.action as "BUY" | "SELL",
        price: Number(t.price),
        shares: Number(t.shares),
        sizeUsd: Number(t.size_usd),
        realizedPnl: Number(t.realized_pnl),
        cashAfter: Number(t.cash_after),
        reason: (t.reason as string | null) ?? "",
        createdAt: t.created_at as string,
      })),
    };
  });

/** Dry risk-gate evaluation shown before an order is submitted. */
export const checkPaperGates = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) =>
    z.object({ market: z.string().min(1), sizeUsd: z.number().positive() }).parse(input),
  )
  .handler(async ({ data, context }) => {
    const ctx = context as unknown as Ctx;
    const account = await loadAccount(ctx);
    const gates = await evaluateGates(ctx, account, data.market, data.sizeUsd);
    return { gates, allowed: gates.every((g) => g.allowed) };
  });

/** Paper BUY — gated, updates cash and the position's weighted average price. */
export const paperBuy = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) =>
    z
      .object({
        market: z.string().min(1),
        side: z.enum(["UP", "DOWN"]),
        price: z.number().gt(0).lte(1),
        sizeUsd: z.number().positive().max(1_000_000),
        reason: z.string().max(200).default("manual paper buy"),
      })
      .parse(input),
  )
  .handler(async ({ data, context }) => {
    const ctx = context as unknown as Ctx;
    const account = await loadAccount(ctx);
    const gates = await evaluateGates(ctx, account, data.market, data.sizeUsd);
    if (!gates.every((g) => g.allowed)) {
      return { status: "blocked" as const, gates };
    }

    const shares = data.sizeUsd / data.price;
    const { data: existing } = await ctx.supabase
      .from("paper_positions")
      .select("*")
      .eq("user_id", ctx.userId)
      .eq("market", data.market)
      .eq("side", data.side)
      .maybeSingle();

    if (existing) {
      const totalShares = Number(existing.shares) + shares;
      const totalCost = Number(existing.cost_usd) + data.sizeUsd;
      const { error } = await ctx.supabase
        .from("paper_positions")
        .update({
          shares: totalShares,
          cost_usd: totalCost,
          avg_price: totalCost / totalShares,
          updated_at: new Date().toISOString(),
        })
        .eq("id", existing.id);
      if (error) throw new Error(error.message);
    } else {
      const { error } = await ctx.supabase.from("paper_positions").insert({
        user_id: ctx.userId,
        market: data.market,
        side: data.side,
        shares,
        avg_price: data.price,
        cost_usd: data.sizeUsd,
      });
      if (error) throw new Error(error.message);
    }

    const cashAfter = Number(account.cash) - data.sizeUsd;
    const { error: accountError } = await ctx.supabase
      .from("paper_accounts")
      .update({ cash: cashAfter, updated_at: new Date().toISOString() })
      .eq("user_id", ctx.userId);
    if (accountError) throw new Error(accountError.message);

    await ctx.supabase.from("paper_trades").insert({
      user_id: ctx.userId,
      market: data.market,
      side: data.side,
      action: "BUY",
      price: data.price,
      shares,
      size_usd: data.sizeUsd,
      realized_pnl: 0,
      cash_after: cashAfter,
      reason: data.reason,
      gates,
    });

    return { status: "filled" as const, gates, shares, cashAfter };
  });

/** Paper SELL / close — realizes P&L on part or all of a position. */
export const paperSell = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) =>
    z
      .object({
        positionId: z.string().uuid(),
        price: z.number().gt(0).lte(1),
        fraction: z.number().gt(0).lte(1).default(1),
        reason: z.string().max(200).default("manual paper close"),
      })
      .parse(input),
  )
  .handler(async ({ data, context }) => {
    const ctx = context as unknown as Ctx;
    const account = await loadAccount(ctx);
    const { data: position, error } = await ctx.supabase
      .from("paper_positions")
      .select("*")
      .eq("user_id", ctx.userId)
      .eq("id", data.positionId)
      .maybeSingle();
    if (error) throw new Error(error.message);
    if (!position) return { status: "not_found" as const };

    const sharesSold = Number(position.shares) * data.fraction;
    const costPortion = Number(position.cost_usd) * data.fraction;
    const proceeds = sharesSold * data.price;
    const realized = Math.round((proceeds - costPortion) * 100) / 100;

    if (data.fraction >= 0.999999) {
      await ctx.supabase.from("paper_positions").delete().eq("id", position.id);
    } else {
      await ctx.supabase
        .from("paper_positions")
        .update({
          shares: Number(position.shares) - sharesSold,
          cost_usd: Number(position.cost_usd) - costPortion,
          updated_at: new Date().toISOString(),
        })
        .eq("id", position.id);
    }

    const cashAfter = Number(account.cash) + proceeds;
    await ctx.supabase
      .from("paper_accounts")
      .update({
        cash: cashAfter,
        realized_pnl: Number(account.realized_pnl) + realized,
        updated_at: new Date().toISOString(),
      })
      .eq("user_id", ctx.userId);

    await ctx.supabase.from("paper_trades").insert({
      user_id: ctx.userId,
      market: position.market,
      side: position.side,
      action: "SELL",
      price: data.price,
      shares: sharesSold,
      size_usd: Math.round(proceeds * 100) / 100,
      realized_pnl: realized,
      cash_after: cashAfter,
      reason: data.reason,
    });

    return { status: "closed" as const, realized, proceeds, cashAfter };
  });

/** Wipe positions and ledger, restore the starting bankroll. */
export const resetPaperAccount = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) =>
    z
      .object({ startingBankroll: z.number().positive().max(10_000_000).default(DEFAULT_BANKROLL) })
      .parse(input ?? {}),
  )
  .handler(async ({ data, context }) => {
    const ctx = context as unknown as Ctx;
    await loadAccount(ctx);
    await ctx.supabase.from("paper_positions").delete().eq("user_id", ctx.userId);
    await ctx.supabase.from("paper_trades").delete().eq("user_id", ctx.userId);
    const { error } = await ctx.supabase
      .from("paper_accounts")
      .update({
        starting_bankroll: data.startingBankroll,
        cash: data.startingBankroll,
        realized_pnl: 0,
        updated_at: new Date().toISOString(),
      })
      .eq("user_id", ctx.userId);
    if (error) throw new Error(error.message);
    return { status: "reset" as const, startingBankroll: data.startingBankroll };
  });

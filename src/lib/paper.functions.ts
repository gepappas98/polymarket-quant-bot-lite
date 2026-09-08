import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";
import { PaperAdapter } from "@/lib/execution/paperAdapter";
import { applyPlaceResult, createOrder } from "@/lib/execution/orderExecutor";
import { systemClock } from "@/lib/execution/clock";

export interface PaperGate {
  name: string;
  allowed: boolean;
  reason: string;
}

const DEFAULT_BANKROLL = 10_000;

type Ctx = { supabase: any; userId: string };

async function loadAccount(ctx: Ctx) {
  const { data: existing, error } = await ctx.supabase
    .from("paper_account")
    .select("*")
    .eq("user_id", ctx.userId)
    .maybeSingle();
  if (error) throw new Error(error.message);
  if (existing) return existing;
  const { data: created, error: insertError } = await ctx.supabase
    .from("paper_account")
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
    const [positionsResult, tradesResult] = await Promise.all([
      ctx.supabase.from("paper_positions").select("*").eq("user_id", ctx.userId).order("opened_at", { ascending: false }),
      ctx.supabase.from("paper_trades").select("*").eq("user_id", ctx.userId).order("created_at", { ascending: false }).limit(100),
    ]);
    if (positionsResult.error) throw new Error(positionsResult.error.message);
    if (tradesResult.error) throw new Error(tradesResult.error.message);
    const positions = positionsResult.data;
    const trades = tradesResult.data;
    const dailyPnl = await todayRealized(ctx);
    return {
      engine: "paper" as const,
      account: { startingBankroll: Number(account.starting_bankroll), cash: Number(account.cash), realizedPnl: Number(account.realized_pnl), dailyPnl, dailyLossLimit: Number(account.daily_loss_limit), maxPositionPct: Number(account.max_position_pct), cooldownSeconds: Number(account.cooldown_seconds) },
      positions: (positions ?? []).map((p: any) => ({ id: p.id, market: p.market, side: p.side, shares: Number(p.shares), avgPrice: Number(p.avg_price), costUsd: Number(p.cost_usd), openedAt: p.opened_at })),
      trades: (trades ?? []).map((t: any) => ({ id: t.id, market: t.market, side: t.side, action: t.action, price: Number(t.price), shares: Number(t.shares), sizeUsd: Number(t.size_usd), realizedPnl: Number(t.realized_pnl), cashAfter: Number(t.cash_after), reason: t.reason ?? "", createdAt: t.created_at })),
    };
  });

/** Dry risk-gate evaluation shown before an order is submitted. */
export const checkPaperGates = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) => z.object({ market: z.string().min(1), sizeUsd: z.number().positive() }).parse(input))
  .handler(async ({ data, context }) => {
    const ctx = context as unknown as Ctx;
    const account = await loadAccount(ctx);
    const gates = await evaluateGates(ctx, account, data.market, data.sizeUsd);
    return { gates, allowed: gates.every((g) => g.allowed) };
  });

/** Canonical Paper execution path: risk gates -> OrderExecutor -> PaperAdapter -> order/fills -> account/position ledger. */
export const executePaperOrder = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) => z.object({
    action: z.enum(["BUY", "SELL"]),
    market: z.string().min(1),
    side: z.enum(["UP", "DOWN"]),
    price: z.number().gt(0).lte(1),
    sizeUsd: z.number().positive().max(1_000_000),
    positionId: z.string().uuid().optional(),
    clientOrderId: z.string().min(1).max(128),
    reason: z.string().max(200).default("manual paper order"),
  }).parse(input))
  .handler(async ({ data, context }) => {
    const ctx = context as unknown as Ctx;
    const account = await loadAccount(ctx);
    const gates = data.action === "BUY" ? await evaluateGates(ctx, account, data.market, data.sizeUsd) : [];
    if (gates.length && !gates.every((gate) => gate.allowed)) return { status: "blocked" as const, gates };

    const existingOrder = await ctx.supabase.from("paper_orders").select("*").eq("user_id", ctx.userId).eq("client_order_id", data.clientOrderId).maybeSingle();
    if (existingOrder.error) throw new Error(existingOrder.error.message);
    if (existingOrder.data) return { status: "already_filled" as const, orderId: existingOrder.data.id, state: existingOrder.data.state, filledShares: Number(existingOrder.data.filled_shares), remainingShares: Number(existingOrder.data.remaining_shares), avgFillPrice: Number(existingOrder.data.avg_fill_price), fees: Number(existingOrder.data.fees), slippage: Number(existingOrder.data.slippage), timestamp: existingOrder.data.updated_at };

    let requestedShares = data.sizeUsd / data.price;
    let position: any = null;
    if (data.action === "SELL") {
      const positionResult = await ctx.supabase.from("paper_positions").select("*").eq("user_id", ctx.userId).eq("id", data.positionId ?? "").maybeSingle();
      if (positionResult.error) throw new Error(positionResult.error.message);
      position = positionResult.data;
      if (!position) return { status: "rejected" as const, reason: "position not found" };
      requestedShares = Number(position.shares);
    }

    const adapter = new PaperAdapter({ [data.market]: data.action === "BUY" ? { asks: [{ price: data.price, shares: requestedShares }] } : { bids: [{ price: data.price, shares: requestedShares }] } }, systemClock);
    const request = { clientOrderId: data.clientOrderId, market: data.market, side: data.side, action: data.action, orderType: "MARKET" as const, price: data.price, sizeShares: requestedShares, mode: "paper" as const };
    const order = createOrder(request, systemClock, data.clientOrderId);
    const venueResult = await adapter.placeOrder(request);
    const executed = applyPlaceResult(order, venueResult, systemClock);
    const filledShares = executed.filledShares;
    const notional = executed.fills.reduce((sum, fill) => sum + fill.price * fill.shares, 0);
    const fees = executed.feesPaid;
    const proceedsOrCost = notional + (data.action === "BUY" ? fees : -fees);
    const avgFillPrice = executed.avgFillPrice;
    const orderInsert = await ctx.supabase.from("paper_orders").insert({ user_id: ctx.userId, client_order_id: data.clientOrderId, market: data.market, side: data.side, action: data.action, order_type: "MARKET", requested_shares: requestedShares, filled_shares: filledShares, remaining_shares: Math.max(0, requestedShares - filledShares), avg_fill_price: avgFillPrice, fees, slippage: avgFillPrice - data.price, state: executed.status, reason: data.reason }).select("id, updated_at").single();
    if (orderInsert.error) throw new Error(orderInsert.error.message);
    if (executed.fills.length) {
      const fillsInsert = await ctx.supabase.from("paper_order_fills").insert(executed.fills.map((fill) => ({ order_id: orderInsert.data.id, user_id: ctx.userId, price: fill.price, shares: fill.shares, fee: fill.fee, filled_at: fill.filledAt })));
      if (fillsInsert.error) throw new Error(fillsInsert.error.message);
    }

    let realized = 0;
    if (data.action === "BUY") {
      const current = await ctx.supabase.from("paper_positions").select("*").eq("user_id", ctx.userId).eq("market", data.market).eq("side", data.side).maybeSingle();
      const oldShares = Number(current.data?.shares ?? 0); const oldCost = Number(current.data?.cost_usd ?? 0); const newCost = oldCost + notional + fees; const newShares = oldShares + filledShares;
      const positionWrite = current.data ? ctx.supabase.from("paper_positions").update({ shares: newShares, cost_usd: newCost, avg_price: newCost / newShares, updated_at: new Date().toISOString() }).eq("id", current.data.id) : ctx.supabase.from("paper_positions").insert({ user_id: ctx.userId, market: data.market, side: data.side, shares: newShares, avg_price: newCost / newShares, cost_usd: newCost });
      const writeResult = await positionWrite; if (writeResult.error) throw new Error(writeResult.error.message);
    } else {
      const costPortion = Number(position.cost_usd) * (filledShares / Number(position.shares)); realized = Math.round((notional - fees - costPortion) * 100) / 100;
      const remaining = Number(position.shares) - filledShares;
      const writeResult = remaining <= 1e-8 ? await ctx.supabase.from("paper_positions").delete().eq("id", position.id) : await ctx.supabase.from("paper_positions").update({ shares: remaining, cost_usd: Number(position.cost_usd) - costPortion, updated_at: new Date().toISOString() }).eq("id", position.id);
      if (writeResult.error) throw new Error(writeResult.error.message);
    }
    const cashAfter = Number(account.cash) + (data.action === "BUY" ? -proceedsOrCost : proceedsOrCost);
    const accountWrite = await ctx.supabase.from("paper_account").update({ cash: cashAfter, realized_pnl: Number(account.realized_pnl) + realized, updated_at: new Date().toISOString() }).eq("user_id", ctx.userId);
    if (accountWrite.error) throw new Error(accountWrite.error.message);
    const tradeWrite = await ctx.supabase.from("paper_trades").insert({ user_id: ctx.userId, market: data.market, side: data.side, action: data.action, price: avgFillPrice, shares: filledShares, size_usd: notional, realized_pnl: realized, cash_after: cashAfter, reason: data.reason, gates, client_order_id: data.clientOrderId, execution_mode: "paper" });
    if (tradeWrite.error) throw new Error(tradeWrite.error.message);
    return { status: executed.status === "FILLED" ? "filled" as const : "partial" as const, orderId: orderInsert.data.id, state: executed.status, requestedShares, filledShares, remainingShares: requestedShares - filledShares, avgFillPrice, fees, slippage: avgFillPrice - data.price, timestamp: orderInsert.data.updated_at, position: data.market, realizedPnl: realized, unrealizedPnl: 0, reason: data.reason, cashAfter };
  });

/** Paper BUY — compatibility wrapper. Canonical UI execution uses executePaperOrder. */
export const paperBuy = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) =>
    z
      .object({
        market: z.string().min(1),
        side: z.enum(["UP", "DOWN"]),
        price: z.number().gt(0).lte(1),
        sizeUsd: z.number().positive().max(1_000_000),
        clientOrderId: z.string().min(1).max(128).optional(),
        reason: z.string().max(200).default("manual paper buy"),
      })
      .parse(input),
  )
  .handler(async ({ data, context }) => {
    const ctx = context as unknown as Ctx;
    if (data.clientOrderId) {
      const { data: prior, error: priorError } = await ctx.supabase
        .from("paper_trades")
        .select("id, shares, cash_after")
        .eq("user_id", ctx.userId)
        .eq("client_order_id", data.clientOrderId)
        .maybeSingle();
      if (priorError) throw new Error(priorError.message);
      if (prior) {
        return { status: "already_filled" as const, tradeId: prior.id, shares: Number(prior.shares), cashAfter: Number(prior.cash_after) };
      }
    }
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
      .from("paper_account")
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
      client_order_id: data.clientOrderId ?? null,
      execution_mode: "paper",
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
      .from("paper_account")
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
      .from("paper_account")
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

export type PaperOrderFillRow = { id: string; price: number; shares: number; fee: number; filledAt: string };
export type PaperOrderRow = {
  id: string;
  clientOrderId: string;
  market: string;
  side: string;
  action: string;
  state: string;
  requestedShares: number;
  filledShares: number;
  remainingShares: number;
  avgFillPrice: number;
  fees: number;
  slippage: number;
  reason: string;
  createdAt: string;
  fills: PaperOrderFillRow[];
};

/** Order blotter: every paper order with its fills. */
export const listPaperOrders = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) => z.object({ limit: z.number().int().min(1).max(500).default(100) }).parse(input ?? {}))
  .handler(async ({ data, context }): Promise<PaperOrderRow[]> => {
    const ctx = context as unknown as Ctx;
    const orders = await ctx.supabase
      .from("paper_orders")
      .select("*")
      .eq("user_id", ctx.userId)
      .order("created_at", { ascending: false })
      .limit(data.limit);
    if (orders.error) throw new Error(orders.error.message);
    const ids = (orders.data ?? []).map((o: any) => o.id);
    let fills: any[] = [];
    if (ids.length) {
      const fillsResult = await ctx.supabase
        .from("paper_order_fills")
        .select("*")
        .eq("user_id", ctx.userId)
        .in("order_id", ids);
      if (fillsResult.error) throw new Error(fillsResult.error.message);
      fills = fillsResult.data ?? [];
    }
    return (orders.data ?? []).map((o: any) => ({
      id: o.id,
      clientOrderId: o.client_order_id,
      market: o.market,
      side: o.side,
      action: o.action,
      state: o.state,
      requestedShares: Number(o.requested_shares),
      filledShares: Number(o.filled_shares),
      remainingShares: Number(o.remaining_shares),
      avgFillPrice: Number(o.avg_fill_price ?? 0),
      fees: Number(o.fees ?? 0),
      slippage: Number(o.slippage ?? 0),
      reason: o.reason ?? "",
      createdAt: o.created_at,
      fills: fills
        .filter((f) => f.order_id === o.id)
        .map((f) => ({ id: f.id, price: Number(f.price), shares: Number(f.shares), fee: Number(f.fee ?? 0), filledAt: f.filled_at })),
    }));
  });

/** Filterable paper trade history. */
export const getPaperHistory = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) =>
    z.object({ market: z.string().optional(), action: z.enum(["BUY", "SELL"]).optional(), limit: z.number().int().min(1).max(500).default(200) }).parse(input ?? {}),
  )
  .handler(async ({ data, context }) => {
    const ctx = context as unknown as Ctx;
    let query = ctx.supabase
      .from("paper_trades")
      .select("*")
      .eq("user_id", ctx.userId)
      .order("created_at", { ascending: false })
      .limit(data.limit);
    if (data.market) query = query.eq("market", data.market);
    if (data.action) query = query.eq("action", data.action);
    const { data: rows, error } = await query;
    if (error) throw new Error(error.message);
    type HistoryTrade = {
      id: string;
      market: string;
      side: string;
      action: string;
      price: number;
      shares: number;
      sizeUsd: number;
      realizedPnl: number;
      cashAfter: number;
      reason: string;
      createdAt: string;
    };
    const trades: HistoryTrade[] = (rows ?? []).map((t: any) => ({
      id: t.id,
      market: t.market,
      side: t.side,
      action: t.action,
      price: Number(t.price),
      shares: Number(t.shares),
      sizeUsd: Number(t.size_usd),
      realizedPnl: Number(t.realized_pnl),
      cashAfter: Number(t.cash_after),
      reason: t.reason ?? "",
      createdAt: t.created_at,
    }));
    const wins = trades.filter((t) => t.action === "SELL" && t.realizedPnl > 0).length;
    const closed = trades.filter((t) => t.action === "SELL").length;
    return {
      trades,
      stats: {
        count: trades.length,
        closed,
        wins,
        winRate: closed ? wins / closed : 0,
        realizedPnl: trades.reduce((s, t) => s + t.realizedPnl, 0),
        volumeUsd: trades.reduce((s, t) => s + t.sizeUsd, 0),
      },
    };
  });

/** Reconcile the paper account: recompute cash / realized P&L from the trade ledger and repair order states. */
export const reconcilePaperAccount = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((input) => z.object({ apply: z.boolean().default(false) }).parse(input ?? {}))
  .handler(async ({ data, context }) => {
    const ctx = context as unknown as Ctx;
    const account = await loadAccount(ctx);
    const [tradesResult, positionsResult, ordersResult] = await Promise.all([
      ctx.supabase.from("paper_trades").select("*").eq("user_id", ctx.userId),
      ctx.supabase.from("paper_positions").select("*").eq("user_id", ctx.userId),
      ctx.supabase.from("paper_orders").select("*").eq("user_id", ctx.userId),
    ]);
    if (tradesResult.error) throw new Error(tradesResult.error.message);
    if (positionsResult.error) throw new Error(positionsResult.error.message);
    if (ordersResult.error) throw new Error(ordersResult.error.message);
    const trades = tradesResult.data ?? [];
    const positions = positionsResult.data ?? [];
    const orders = ordersResult.data ?? [];

    let cash = Number(account.starting_bankroll);
    let realized = 0;
    for (const t of trades) {
      const notional = Number(t.size_usd);
      cash += t.action === "BUY" ? -notional : notional;
      realized += Number(t.realized_pnl);
    }
    const positionCost = positions.reduce((s: number, p: any) => s + Number(p.cost_usd), 0);
    const orphanOrders = orders.filter(
      (o: any) => !trades.some((t: any) => t.client_order_id && t.client_order_id === o.client_order_id),
    );
    const cashDrift = Math.round((cash - Number(account.cash)) * 100) / 100;
    const realizedDrift = Math.round((realized - Number(account.realized_pnl)) * 100) / 100;

    let applied = false;
    if (data.apply && (Math.abs(cashDrift) > 0.005 || Math.abs(realizedDrift) > 0.005)) {
      const { error } = await ctx.supabase
        .from("paper_account")
        .update({ cash, realized_pnl: realized, updated_at: new Date().toISOString() })
        .eq("user_id", ctx.userId);
      if (error) throw new Error(error.message);
      applied = true;
    }

    return {
      checkedAt: new Date().toISOString(),
      ledger: { trades: trades.length, orders: orders.length, positions: positions.length },
      account: { cash: Number(account.cash), realizedPnl: Number(account.realized_pnl), startingBankroll: Number(account.starting_bankroll) },
      computed: { cash: Math.round(cash * 100) / 100, realizedPnl: Math.round(realized * 100) / 100, positionCost: Math.round(positionCost * 100) / 100, equity: Math.round((cash + positionCost) * 100) / 100 },
      drift: { cash: cashDrift, realizedPnl: realizedDrift },
      orphanOrders: orphanOrders.map((o: any) => ({ id: o.id, clientOrderId: o.client_order_id, market: o.market, state: o.state, createdAt: o.created_at })) as Array<{ id: string; clientOrderId: string; market: string; state: string; createdAt: string }>,
      inSync: Math.abs(cashDrift) <= 0.005 && Math.abs(realizedDrift) <= 0.005 && orphanOrders.length === 0,
      applied,
    };
  });

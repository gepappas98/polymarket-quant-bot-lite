import threading
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select

from app.models.trade import Trade
from app.services.execution_service import get_executor
from app.services.risk_service import evaluate_safety_gates, get_or_create_risk_config, simulate_trailing_stop
from app.services.strategy_service import get_active_strategies, should_ignore_market
from app.services.sizing_service import calculate_kelly_size, odds_from_price
from app.services.websocket_manager import manager
from app.utils.categories import category_for_slug
from bot.config import cfg
from bot.strategy import Intent, Side

_trade_lock = threading.Lock()


@dataclass
class PlaceOrderResult:
    status: str
    market_slug: str
    category: str
    size_usd: float
    f_value: float
    reasons: List[str]
    fill: Optional[dict]
    trade_id: Optional[int]
    dry_run: bool


@dataclass
class CloseTradeResult:
    status: str
    trade_id: int
    size_usd: float
    pnl_usd: Optional[float]
    reason: str
    fill: Optional[dict]
    dry_run: bool


def place_order(*, market_slug, token_id, side, price, confidence, balance, user_id=1, db, category=None, reason="api", executor=None):
    normalized_side = str(side).upper() if isinstance(side, str) else ""
    if normalized_side not in ("UP", "DOWN"):
        raise ValueError("side must be UP or DOWN")
    category = category or category_for_slug(market_slug)
    with _trade_lock:
        active = get_active_strategies(db, user_id)
        if should_ignore_market(market_slug, category, active):
            return PlaceOrderResult("ignored", market_slug, category, 0.0, 0.0, ["market ignored by active strategy"], None, None, cfg.mode != "live")
        config = get_or_create_risk_config(db, user_id)
        initial = evaluate_safety_gates(user_id, db, market_slug, category)
        if initial.blocks:
            return PlaceOrderResult("blocked", market_slug, category, 0.0, 0.0, initial.blocks, None, None, cfg.mode != "live")
        sizing = calculate_kelly_size(confidence, odds_from_price(price), category, balance, config.k_value, config.max_position_pct)
        if sizing.suggested_amount <= 0:
            return PlaceOrderResult("blocked", market_slug, category, 0.0, sizing.f_value, ["kelly size is zero"], None, None, cfg.mode != "live")
        gated = evaluate_safety_gates(user_id, db, market_slug, category, sizing.suggested_amount)
        if gated.blocks:
            return PlaceOrderResult("blocked", market_slug, category, sizing.suggested_amount, sizing.f_value, gated.blocks, None, None, cfg.mode != "live")
        outcome_side = Side(normalized_side)
        intent = Intent(market_slug, str(token_id), outcome_side, "BUY", float(price), sizing.suggested_amount, f"{reason} kelly f={sizing.f_value:.2f}%")
        fills = (executor or get_executor()).execute([intent])
        if not fills:
            return PlaceOrderResult("no_fill", market_slug, category, sizing.suggested_amount, sizing.f_value, ["executor returned no fill"], None, None, cfg.mode != "live")
        fill = fills[0]
        trade = Trade(market_slug=market_slug, token_id=str(token_id), category=category, side=normalized_side, entry_price=fill.avg_price, size_usd=fill.cost, current_price=fill.avg_price, status="open", dry_run=fill.simulated, order_id=fill.order_id, reason=reason)
        db.add(trade)
        db.commit()
        db.refresh(trade)
        from app.services.risk_service import advanced_cooldown
        advanced_cooldown.check_and_lock(market_slug)
        payload = {"type": "position_opened", "trade_id": trade.id, "market_slug": market_slug, "size_usd": trade.size_usd}
        manager.broadcast_sync(payload)
        manager.broadcast_sync({"type": "circuit_breaker", "status": evaluate_safety_gates(user_id, db).gates[0].status})
        return PlaceOrderResult("filled", market_slug, category, fill.cost, sizing.f_value, [], {"order_id": fill.order_id, "price": fill.avg_price, "shares": fill.shares}, trade.id, fill.simulated)


def close_trailing_stop(trade_id: int, current_price: float, *, db, executor=None) -> CloseTradeResult:
    """Close an open position when its configured adverse-move threshold is reached."""
    with _trade_lock:
        trade = db.get(Trade, trade_id)
        if trade is None:
            raise ValueError(f"trade {trade_id} not found")
        if trade.status != "open":
            return CloseTradeResult("already_closed", trade.id, 0.0, trade.pnl_usd, "trade is not open", None, trade.dry_run)
        current = float(current_price)
        signal = simulate_trailing_stop(trade.id, current, db)
        trade.current_price = current
        if not signal.should_close:
            db.commit()
            return CloseTradeResult("held", trade.id, 0.0, None, "trailing-stop threshold not reached", None, trade.dry_run)
        token_id = trade.token_id or ""
        shares = float(trade.size_usd) / max(float(trade.entry_price), 1e-9)
        close_notional = shares * current
        intent = Intent(trade.market_slug, token_id, Side(str(trade.side).upper()), "SELL", current, close_notional, "trailing stop")
        fills = (executor or get_executor()).execute([intent])
        if not fills:
            db.commit()
            return CloseTradeResult("no_fill", trade.id, close_notional, None, "executor returned no fill", None, trade.dry_run)
        fill = fills[0]
        proceeds = round(float(fill.cost), 2)
        pnl = round(proceeds - float(trade.size_usd), 2)
        trade.status = "closed"
        trade.closed_at = __import__("datetime").datetime.utcnow()
        trade.current_price = fill.avg_price
        trade.pnl_usd = pnl
        db.commit()
        manager.broadcast_sync({"type": "position_closed", "trade_id": trade.id, "market_slug": trade.market_slug, "pnl_usd": pnl, "reason": "trailing stop"})
        return CloseTradeResult("closed", trade.id, proceeds, pnl, "trailing stop", {"order_id": fill.order_id, "price": fill.avg_price, "shares": fill.shares}, fill.simulated)


def process_price_update(trade_id: int, current_price: float, *, db, executor=None) -> CloseTradeResult:
    """Persist a market price and evaluate the trailing stop for that position."""
    trade = db.get(Trade, trade_id)
    if trade is None:
        raise ValueError(f"trade {trade_id} not found")
    if trade.status != "open":
        trade.current_price = float(current_price)
        db.commit()
        return CloseTradeResult("already_closed", trade.id, 0.0, trade.pnl_usd, "trade is not open", None, trade.dry_run)
    return close_trailing_stop(trade_id, current_price, db=db, executor=executor)

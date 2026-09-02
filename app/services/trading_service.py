from dataclasses import dataclass
import threading
from typing import List, Optional
from sqlalchemy import select

from app.models.trade import Trade
from app.services.execution_service import get_executor
from app.services.risk_service import evaluate_safety_gates, get_or_create_risk_config
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
        trade = Trade(market_slug=market_slug, category=category, side=normalized_side, entry_price=fill.avg_price, size_usd=fill.cost, status="open", dry_run=fill.simulated, order_id=fill.order_id, reason=reason)
        db.add(trade)
        db.commit()
        db.refresh(trade)
        from app.services.risk_service import advanced_cooldown
        advanced_cooldown.check_and_lock(market_slug)
        payload = {"type": "position_opened", "trade_id": trade.id, "market_slug": market_slug, "size_usd": trade.size_usd}
        manager.broadcast_sync(payload)
        manager.broadcast_sync({"type": "circuit_breaker", "status": evaluate_safety_gates(user_id, db).gates[0].status})
        return PlaceOrderResult("filled", market_slug, category, fill.cost, sizing.f_value, [], {"order_id": fill.order_id, "price": fill.avg_price, "shares": fill.shares}, trade.id, fill.simulated)

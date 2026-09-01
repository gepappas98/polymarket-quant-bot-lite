from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import Dict, List, Optional

from sqlalchemy import select

from app.core import database
from app.ledger.reader import trade_history, daily_pnl
from app.models.risk_config import RiskConfig
from app.models.trade import Trade
from app.utils.categories import category_for_slug
from bot import daily_limit, gates, portfolio_gates


@dataclass
class GateStatus:
    name: str
    status: str
    reason: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class TrailingStopSignal:
    trade_id: int
    should_close: bool
    entry_price: float
    current_price: float
    move_pct: float
    threshold_pct: float


@dataclass
class SafetyGateReport:
    allowed: bool
    blocks: List[str]
    warnings: List[str]
    gates: List[GateStatus]
    category_exposure: Dict[str, dict]
    trailing_stops: List[TrailingStopSignal]


def get_or_create_risk_config(db, user_id=1):
    row = db.scalar(select(RiskConfig).where(RiskConfig.user_id == user_id))
    if row is None:
        row = RiskConfig(user_id=user_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def check_circuit_breaker(user_id, db, now_ts=None):
    config = get_or_create_risk_config(db, user_id)
    ledger_pnl = daily_pnl(now_ts if now_ts is not None else None)
    bot_pnl = daily_limit.current_daily_pnl()
    pnl = min(ledger_pnl, bot_pnl)
    detail = {"daily_pnl": pnl, "limit": config.daily_loss_limit}
    if not config.enable_circuit_breaker:
        return GateStatus("circuit_breaker", "DISABLED", "circuit breaker disabled", detail)
    if pnl <= config.daily_loss_limit:
        return GateStatus("circuit_breaker", "BLOCKED", "daily loss limit reached", detail)
    return GateStatus("circuit_breaker", "OK", "daily loss limit not reached", detail)


def check_time_window(user_id, db, now=None):
    config = get_or_create_risk_config(db, user_id)
    current = now or datetime.now(timezone.utc)
    start, end = config.enabled_time_start, config.enabled_time_end
    detail = {"start": start, "end": end, "now": current.strftime("%H:%M")}
    if not config.enable_time_window:
        return GateStatus("time_window", "DISABLED", "time window disabled", detail)
    try:
        start_t = time.fromisoformat(start)
        end_t = time.fromisoformat(end)
        current_t = current.time().replace(second=0, microsecond=0)
        allowed = (start_t <= current_t <= end_t) if start_t <= end_t else (current_t >= start_t or current_t <= end_t)
    except ValueError:
        allowed = False
        detail["error"] = "invalid HH:MM window"
    return GateStatus("time_window", "OK" if allowed else "BLOCKED", "" if allowed else "outside enabled time window", detail)


def simulate_trailing_stop(trade_id, current_price, db):
    trade = db.get(Trade, trade_id)
    if trade is None:
        raise ValueError(f"trade {trade_id} not found")
    entry = float(trade.entry_price)
    current = float(current_price)
    is_sell = str(trade.side).upper() in ("SELL", "NO")
    move = ((current - entry) / entry * 100) if is_sell else ((entry - current) / entry * 100)
    threshold = 5.0
    try:
        config = get_or_create_risk_config(db)
        threshold = float(config.trailing_stop_pct)
    except Exception:
        pass
    return TrailingStopSignal(trade_id, move >= threshold, entry, current, move, threshold)


def category_exposure(db, user_id=1):
    config = get_or_create_risk_config(db, user_id)
    values = {category: 0.0 for category in ("politics", "sports", "crypto", "other")}
    for trade in db.scalars(select(Trade).where(Trade.status == "open")).all():
        values[trade.category or category_for_slug(trade.market_slug)] += float(trade.size_usd or 0)
    for row in trade_history(status="open"):
        category = row["category"]
        if not any(t.order_id == row.get("order_id") for t in db.scalars(select(Trade).where(Trade.status == "open")).all()):
            values[category] += float(row.get("size_usd") or 0)
    ceilings = {"politics": config.category_ceiling_politics, "sports": config.category_ceiling_sports, "crypto": None, "other": None}
    return {category: {"exposure": round(exposure, 2), "ceiling": ceilings[category], "remaining": None if ceilings[category] is None else round(ceilings[category] - exposure, 2)} for category, exposure in values.items()}


def evaluate_safety_gates(user_id, db, market_slug=None, category=None, size_usd=None, current_prices=None):
    category = category or (category_for_slug(market_slug) if market_slug else None)
    report_gates = [check_circuit_breaker(user_id, db), check_time_window(user_id, db)]
    config = get_or_create_risk_config(db, user_id)
    exposure = category_exposure(db, user_id)
    if category and size_usd is not None and config.enable_category_ceiling and exposure[category]["ceiling"] is not None:
        projected = exposure[category]["exposure"] + size_usd
        ceiling = exposure[category]["ceiling"]
        status = "BLOCKED" if projected > ceiling else ("WARN" if projected > ceiling * 0.8 else "OK")
        report_gates.append(GateStatus("category_ceiling", status, "category exposure ceiling reached" if status == "BLOCKED" else "", {"category": category, "projected": projected, "ceiling": ceiling}))
    else:
        report_gates.append(GateStatus("category_ceiling", "DISABLED" if not config.enable_category_ceiling else "OK", "", {}))
    daily = daily_limit.check()
    report_gates.append(GateStatus("daily_kill_switch", "OK" if daily.allowed else "BLOCKED", daily.reason or "", {}))
    drawdown = portfolio_gates.max_drawdown_gate()
    report_gates.append(GateStatus("max_drawdown", "OK" if drawdown.allowed else "BLOCKED", drawdown.reason or "", {}))
    live = gates.is_live_trading_allowed()
    report_gates.append(GateStatus("live_trading", "OK" if live.allowed else "WARN", live.reason or "", {"mode": gates.cfg.mode}))
    blocks = [g.reason or g.name for g in report_gates if g.status == "BLOCKED"]
    warnings = [g.reason or g.name for g in report_gates if g.status == "WARN"]
    stops = []
    for trade in db.scalars(select(Trade).where(Trade.status == "open")).all():
        price = (current_prices or {}).get(trade.id, trade.current_price)
        if price is not None:
            signal = simulate_trailing_stop(trade.id, price, db)
            stops.append(signal)
            if signal.should_close:
                warnings.append(f"trailing stop: close trade {trade.id}")
    return SafetyGateReport(not blocks, blocks, warnings, report_gates, exposure, stops)


_advanced_hook = None


def install_bot_gate_hook():
    global _advanced_hook
    if _advanced_hook is not None:
        if _advanced_hook not in gates.extra_checks:
            gates.register_check(_advanced_hook)
        return

    def advanced_check(market_slug, size_usd):
        try:
            with database.SessionLocal() as db:
                category = category_for_slug(market_slug)
                report = evaluate_safety_gates(1, db, market_slug, category, size_usd)
                if report.blocks:
                    return gates.GateResult(False, "; ".join(report.blocks))
                return gates.GateResult(True)
        except Exception as exc:
            return gates.GateResult(False, f"advanced risk engine unavailable: {exc}")
    _advanced_hook = advanced_check
    gates.register_check(_advanced_hook)

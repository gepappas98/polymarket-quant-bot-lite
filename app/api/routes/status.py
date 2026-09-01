from datetime import datetime, timezone
from fastapi import Depends
from app.api.routes import api_router
from app.core.database import get_db
from app.models.trade import Trade
from app.schemas.v04_schemas import GateStatusOut, RiskConfigOut
from app.services.risk_service import check_circuit_breaker, check_time_window, category_exposure, get_or_create_risk_config
from app.services.strategy_service import get_active_strategies, strategy_names
from bot.config import cfg
from bot.gates import is_live_trading_allowed
from app.ledger.reader import daily_pnl


@api_router.get("/status")
def status(db=Depends(get_db)):
    active = get_active_strategies(db)
    circuit = check_circuit_breaker(1, db)
    window = check_time_window(1, db)
    return {
        "mode": cfg.mode,
        "live_trading_allowed": is_live_trading_allowed().allowed,
        "daily_pnl": daily_pnl(),
        "circuit_breaker": GateStatusOut.model_validate(circuit),
        "time_window": GateStatusOut.model_validate(window),
        "active_strategies": strategy_names(active),
        "strategy_flags": active.__dict__,
        "category_exposure": category_exposure(db),
        "open_positions": db.query(Trade).filter(Trade.status == "open").count(),
        "risk_config": RiskConfigOut.model_validate(get_or_create_risk_config(db)),
        "generated_at": datetime.now(timezone.utc),
    }

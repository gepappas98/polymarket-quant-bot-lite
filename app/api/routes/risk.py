import re
from fastapi import Depends, HTTPException
from app.api.routes import api_router
from app.core.database import get_db
from app.schemas.v04_schemas import RiskConfigOut, RiskConfigUpdate, SafetyGateReportOut, TrailingStopRequest, TrailingStopSignalOut
from app.services.risk_service import evaluate_safety_gates, get_or_create_risk_config, simulate_trailing_stop
from app.api.deps import require_api_token


def _out(row):
    return RiskConfigOut.model_validate(row)


@api_router.get("/risk", response_model=RiskConfigOut)
def get_risk(db=Depends(get_db)):
    return _out(get_or_create_risk_config(db))


@api_router.post("/risk/update", response_model=RiskConfigOut)
def update_risk(request: RiskConfigUpdate, db=Depends(get_db), _token=Depends(require_api_token)):
    for key in ("enabled_time_start", "enabled_time_end"):
        value = getattr(request, key)
        if value is not None and not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", value):
            raise HTTPException(422, f"{key} must be HH:MM")
    row = get_or_create_risk_config(db)
    for key, value in request.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _out(row)


@api_router.get("/risk/gates", response_model=SafetyGateReportOut)
def gates(market_slug=None, category=None, size_usd=None, db=Depends(get_db)):
    return evaluate_safety_gates(1, db, market_slug, category, size_usd)


@api_router.post("/risk/trailing-stop", response_model=TrailingStopSignalOut)
def trailing_stop(request: TrailingStopRequest, db=Depends(get_db), _token=Depends(require_api_token)):
    try:
        return simulate_trailing_stop(request.trade_id, request.current_price, db)
    except ValueError as exc:
        raise HTTPException(404, str(exc))

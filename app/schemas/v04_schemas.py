from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class KellySizingRequest(BaseModel):
    confidence: float = Field(..., ge=0, le=1)
    odds: Optional[float] = Field(None, gt=1)
    price: Optional[float] = None
    category: str = "other"
    balance: float = Field(..., gt=0)
    k_value: Optional[float] = Field(None, ge=0, le=1)
    max_position_pct: Optional[float] = Field(None, ge=0, le=1)


class KellySizingResponse(BaseModel):
    suggested_size: float
    suggested_amount: float
    f_value: float
    raw_kelly: float
    variance_used: Optional[float]
    capped_by: Optional[str]
    category: str


class RiskConfigUpdate(BaseModel):
    daily_loss_limit: Optional[float] = None
    cooldown_seconds: Optional[int] = Field(None, ge=0)
    enabled_time_start: Optional[str] = None
    enabled_time_end: Optional[str] = None
    category_ceiling_politics: Optional[float] = None
    category_ceiling_sports: Optional[float] = None
    k_value: Optional[float] = Field(None, ge=0, le=1)
    max_position_pct: Optional[float] = Field(None, ge=0, le=1)
    trailing_stop_pct: Optional[float] = Field(None, ge=0)
    enable_circuit_breaker: Optional[bool] = None
    enable_time_window: Optional[bool] = None
    enable_category_ceiling: Optional[bool] = None
    enable_trailing_stop: Optional[bool] = None


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RiskConfigOut(ORMModel):
    id: int
    user_id: int
    daily_loss_limit: float
    cooldown_seconds: int
    enabled_time_start: str
    enabled_time_end: str
    category_ceiling_politics: float
    category_ceiling_sports: float
    k_value: float
    max_position_pct: float
    trailing_stop_pct: float
    enable_circuit_breaker: bool
    enable_time_window: bool
    enable_category_ceiling: bool
    enable_trailing_stop: bool
    updated_at: Optional[datetime] = None


class GateStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    status: str
    reason: str = ""
    detail: dict = {}


class TrailingStopSignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    trade_id: int
    should_close: bool
    entry_price: float
    current_price: float
    move_pct: float
    threshold_pct: float


class SafetyGateReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    allowed: bool
    blocks: List[str]
    warnings: List[str]
    gates: List[GateStatusOut]
    category_exposure: Dict[str, dict]
    trailing_stops: List[TrailingStopSignalOut]


class TrailingStopRequest(BaseModel):
    trade_id: int
    current_price: float


class StrategyFlags(BaseModel):
    politics_only: bool = False
    sports_fade: bool = False
    crypto_focus: bool = False


class PlaceOrderRequest(BaseModel):
    market_slug: str
    token_id: str
    side: str
    price: float = Field(..., gt=0, lt=1)
    confidence: float = Field(..., ge=0, le=1)
    balance: float = Field(..., gt=0)
    category: Optional[str] = None


class PlaceOrderResponse(BaseModel):
    status: str
    market_slug: str
    category: str
    size_usd: float
    f_value: float
    reasons: List[str]
    fill: Optional[dict]
    trade_id: Optional[int]
    dry_run: bool


class TradeHistoryItem(BaseModel):
    ts: float
    market_slug: str
    category: str
    side: Optional[str] = None
    price: Optional[float] = None
    size_usd: Optional[float] = None
    pnl_usd: Optional[float] = None
    status: str
    dry_run: bool = True
    order_id: Optional[str] = None


class LeaderOut(ORMModel):
    id: int
    address: str
    win_rate: float
    sharpe_ratio: float
    roi: float
    max_drawdown: float
    stability_score: float
    composite_score: float
    trade_count: int
    last_updated: Optional[datetime] = None


RiskConfigResponse = RiskConfigOut
LeaderResponse = LeaderOut


class LeaderboardResponse(BaseModel):
    leaders: List[LeaderOut]
    total_count: int
    refresh_timestamp: datetime


class LeaderboardRefreshRequest(BaseModel):
    force: bool = False


class StrategyUpdateRequest(BaseModel):
    politics_only: Optional[bool] = None
    sports_fade: Optional[bool] = None
    crypto_focus: Optional[bool] = None


class StrategyResponse(StrategyFlags):
    enabled_categories: List[str] = []
    updated_at: Optional[datetime] = None

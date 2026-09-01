"""
Pydantic schemas for new v0.4.0 endpoints.
"""
from typing import Optional, Dict, List
from pydantic import BaseModel, Field
from datetime import datetime


# ===== Sizing Schemas =====
class KellySizingRequest(BaseModel):
    """Request for Kelly sizing calculation."""
    confidence: float = Field(..., ge=0.01, le=0.99, description="Win probability (0-1)")
    odds: float = Field(..., ge=1.0, description="Decimal odds")
    category: str = Field(..., description="Market category (crypto, politics, sports)")
    balance: float = Field(..., gt=0, description="Account balance in USDC")
    k_value: Optional[float] = Field(0.25, ge=0.01, le=1.0, description="Kelly variance cap")
    max_position_pct: Optional[float] = Field(0.05, ge=0.01, le=1.0, description="Max position as % of balance")


class KellySizingResponse(BaseModel):
    """Response from Kelly sizing calculation."""
    suggested_amount: float = Field(..., description="Suggested order size in USDC")
    f_value: float = Field(..., description="Kelly fraction as percentage (0-100)")
    category: str
    confidence: str
    odds: float
    status: str = "success"


# ===== Risk Config Schemas =====
class RiskConfigUpdate(BaseModel):
    """Update request for RiskConfig."""
    daily_loss_limit: Optional[float] = Field(None, description="Daily PnL kill-switch (USDC)")
    cooldown_seconds: Optional[int] = Field(None, ge=0, description="Per-market cooldown")
    enabled_time_start: Optional[str] = Field(None, description="Trading window start (HH:MM)")
    enabled_time_end: Optional[str] = Field(None, description="Trading window end (HH:MM)")
    category_ceiling_politics: Optional[float] = Field(None, gt=0, description="Politics category ceiling (USDC)")
    category_ceiling_sports: Optional[float] = Field(None, gt=0, description="Sports category ceiling (USDC)")
    k_value: Optional[float] = Field(None, ge=0.01, le=1.0, description="Kelly variance cap")
    max_position_pct: Optional[float] = Field(None, ge=0.01, le=1.0, description="Max position %")
    trailing_stop_pct: Optional[float] = Field(None, ge=0.1, le=50.0, description="Trailing stop %")
    enable_circuit_breaker: Optional[bool] = None
    enable_time_window: Optional[bool] = None
    enable_category_ceiling: Optional[bool] = None
    enable_trailing_stop: Optional[bool] = None


class RiskConfigResponse(BaseModel):
    """Full RiskConfig response."""
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
    updated_at: datetime


# ===== Leader Schemas =====
class LeaderResponse(BaseModel):
    """Single leader in leaderboard."""
    id: int
    address: str
    win_rate: float = Field(..., description="Win rate %")
    sharpe_ratio: float
    roi: float = Field(..., description="ROI %")
    max_drawdown: float = Field(..., description="Max drawdown %")
    stability_score: float = Field(..., description="Hampel-filtered consistency 0-100")
    composite_score: float = Field(..., description="Weighted composite score 0-100")
    last_updated: datetime


class LeaderboardResponse(BaseModel):
    """Leaderboard with multiple leaders."""
    leaders: List[LeaderResponse]
    total_count: int
    refresh_timestamp: datetime


class LeaderboardRefreshRequest(BaseModel):
    """Request to refresh leaderboard."""
    force: bool = Field(False, description="Force refresh even if recent")


# ===== Status Schemas =====
class CircuitBreakerStatus(BaseModel):
    """Circuit breaker status."""
    is_blocked: bool
    daily_pnl: float
    daily_loss_limit: float
    reason: Optional[str] = None


class TimeWindowStatus(BaseModel):
    """Trading time window status."""
    is_active: bool
    current_time: str
    window_start: str
    window_end: str


class CategoryExposure(BaseModel):
    """Per-category exposure."""
    category: str
    current_exposure: float
    ceiling: float
    available: float
    is_at_limit: bool


class PortfolioStatus(BaseModel):
    """Overall portfolio/strategy status."""
    daily_pnl: float
    daily_trades: int
    circuit_breaker: CircuitBreakerStatus
    time_window: TimeWindowStatus
    category_exposures: List[CategoryExposure]
    active_positions: int


class StatusResponse(BaseModel):
    """Complete status response."""
    portfolio: PortfolioStatus
    mode: str = Field(..., description="'paper' or 'live'")
    timestamp: datetime


# ===== Trade History Schemas =====
class TradeHistoryFilter(BaseModel):
    """Filter for trade history queries."""
    category: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None  # 'open', 'closed'
    limit: int = Field(100, ge=1, le=1000)


class TradeHistoryEntry(BaseModel):
    """Single trade in history."""
    id: int
    market_slug: str
    category: str
    entry_price: float
    entry_amount: float
    current_price: Optional[float]
    pnl: Optional[float]
    status: str
    created_at: datetime
    closed_at: Optional[datetime]


class TradeHistoryResponse(BaseModel):
    """Trade history response."""
    trades: List[TradeHistoryEntry]
    total_count: int
    filtered_count: int


# ===== Strategy Schemas =====
class StrategyConfig(BaseModel):
    """Strategy configuration."""
    politics_only: bool = False
    sports_fade: bool = False
    crypto_focus: bool = False


class StrategyUpdateRequest(BaseModel):
    """Request to update strategy config."""
    politics_only: Optional[bool] = None
    sports_fade: Optional[bool] = None
    crypto_focus: Optional[bool] = None


class StrategyResponse(BaseModel):
    """Strategy configuration response."""
    politics_only: bool
    sports_fade: bool
    crypto_focus: bool
    enabled_categories: List[str]
    updated_at: datetime

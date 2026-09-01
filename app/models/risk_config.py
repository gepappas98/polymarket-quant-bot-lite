"""
Risk configuration model.

Extended with variance-capped Kelly sizing, category ceilings, and time windows.
"""
from datetime import datetime
from sqlalchemy import Column, Float, Integer, String, DateTime, Boolean
from app.core.database import Base


class RiskConfig(Base):
    """
    Risk configuration settings for a user.
    
    New fields for v0.4.0:
        daily_loss_limit: Daily PnL kill-switch threshold (negative, e.g., -200 USDC)
        cooldown_seconds: Per-market admission cooldown in seconds
        enabled_time_start: HH:MM format for trading window start (e.g., "09:00")
        enabled_time_end: HH:MM format for trading window end (e.g., "17:00")
        category_ceiling_politics: Max exposure in politics category (USDC)
        category_ceiling_sports: Max exposure in sports category (USDC)
        k_value: Variance-cap multiplier for Kelly (0.0-1.0; 1.0 = full Kelly)
        max_position_pct: Maximum position as % of balance (e.g., 0.05 = 5%)
        trailing_stop_pct: Trailing stop threshold, percentage below entry
        enable_circuit_breaker: Enable daily PnL circuit breaker
        enable_time_window: Enable trading time window restrictions
    """
    __tablename__ = "risk_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True, nullable=False)
    
    # Existing risk config fields
    daily_loss_limit = Column(Float, default=-200.0)  # USDC
    cooldown_seconds = Column(Integer, default=180)  # 3 minutes
    
    # New time window fields
    enabled_time_start = Column(String(5), default="00:00")  # HH:MM
    enabled_time_end = Column(String(5), default="23:59")    # HH:MM
    
    # Category-aware exposure ceilings
    category_ceiling_politics = Column(Float, default=500.0)   # USDC
    category_ceiling_sports = Column(Float, default=500.0)     # USDC
    
    # Kelly sizing parameters
    k_value = Column(Float, default=0.25)  # Variance cap: 0.25 = 1/4 Kelly
    max_position_pct = Column(Float, default=0.05)  # 5% of balance per trade
    
    # Trailing stop
    trailing_stop_pct = Column(Float, default=5.0)  # Stop at 5% loss
    
    # Feature toggles
    enable_circuit_breaker = Column(Boolean, default=True)
    enable_time_window = Column(Boolean, default=False)
    enable_category_ceiling = Column(Boolean, default=False)
    enable_trailing_stop = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<RiskConfig(user_id={self.user_id}, "
            f"daily_loss_limit={self.daily_loss_limit}, "
            f"k_value={self.k_value}, "
            f"max_position_pct={self.max_position_pct:.1%})>"
        )

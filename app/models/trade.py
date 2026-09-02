from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from app.core.database import Base


class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, index=True)
    market_slug = Column(String, index=True, nullable=False)
    token_id = Column(String, nullable=True)
    category = Column(String, index=True, nullable=False)
    side = Column(String, nullable=False)
    entry_price = Column(Float, nullable=False)
    size_usd = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    pnl_usd = Column(Float, nullable=True)
    status = Column(String, default="open", nullable=False)
    dry_run = Column(Boolean, default=True, nullable=False)
    order_id = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

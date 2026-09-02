from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer
from app.core.database import Base


class StrategyConfig(Base):
    __tablename__ = "strategy_configs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, default=1, nullable=False)
    politics_only = Column(Boolean, default=False, nullable=False)
    sports_fade = Column(Boolean, default=False, nullable=False)
    crypto_focus = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

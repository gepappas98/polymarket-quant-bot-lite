from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String
from app.core.database import Base


class Leader(Base):
    __tablename__ = "leaders"
    id = Column(Integer, primary_key=True, index=True)
    address = Column(String, unique=True, index=True, nullable=False)
    win_rate = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, default=0.0)
    roi = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    stability_score = Column(Float, default=0.0)
    composite_score = Column(Float, default=0.0)
    trade_count = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)

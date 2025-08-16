from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, CHAR
from sqlalchemy.sql import func
from database import Base

class ShortUrl(Base):
    __tablename__ = "short_urls"
    id = Column(Integer, primary_key=True, index=True)
    short_url = Column(String(10), unique=True, index=True, nullable=False)
    long_url = Column(String(2048), nullable=False)
    user_id = Column(String, index=True, nullable=True)
    visits = Column(Integer, default=0, nullable=False)  # fast counter
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

class Visit(Base):
    __tablename__ = "visits"
    id = Column(Integer, primary_key=True, index=True)
    short_url_id = Column(Integer, ForeignKey("short_urls.id"), nullable=False, index=True)
    visit_time = Column(DateTime, default=func.now(), nullable=False, index=True)
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(String(255), nullable=False)
    referrer = Column(String(2048), nullable=True)
    country = Column(CHAR(2), nullable=True)
    city = Column(String(255), nullable=True)
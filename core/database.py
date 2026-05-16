"""
Database models and session management.
All revenue events, subscriptions, jobs, and leads live here.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, create_engine, func,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from core.config import get_settings

settings = get_settings()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ── Revenue Streams ───────────────────────────────────────────────────────────

class Subscriber(Base):
    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    stripe_customer_id = Column(String(100), unique=True, nullable=True)
    stripe_subscription_id = Column(String(100), unique=True, nullable=True)
    plan = Column(Enum("starter", "pro", "agency", name="plan_enum"), default="starter")
    status = Column(Enum("active", "cancelled", "past_due", name="sub_status"), default="active")
    api_key = Column(String(64), unique=True, nullable=True, index=True)
    api_calls_this_month = Column(Integer, default=0)
    referral_code = Column(String(16), unique=True, nullable=True, index=True)
    referral_credits = Column(Integer, default=0)   # free months earned
    created_at = Column(DateTime(timezone=True), default=utcnow)
    renewed_at = Column(DateTime(timezone=True), nullable=True)
    orders = relationship("Order", back_populates="subscriber")
    api_logs = relationship("ApiLog", back_populates="subscriber")


class Order(Base):
    """One-time purchases (Gumroad digital products)."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    subscriber_id = Column(Integer, ForeignKey("subscribers.id"), nullable=True)
    gumroad_sale_id = Column(String(100), unique=True, nullable=True)
    product_name = Column(String(255), nullable=False)
    amount_usd = Column(Float, nullable=False)
    buyer_email = Column(String(255), nullable=False)
    fulfilled = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    subscriber = relationship("Subscriber", back_populates="orders")


class RevenueEvent(Base):
    """Every dollar that comes in is tracked here."""
    __tablename__ = "revenue_events"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(
        Enum("stripe_subscription", "gumroad_sale", "affiliate", "custom",
             name="revenue_source"),
        nullable=False,
    )
    amount_usd = Column(Float, nullable=False)
    description = Column(String(500), nullable=True)
    external_id = Column(String(200), nullable=True)
    recorded_at = Column(DateTime(timezone=True), default=utcnow)


class ContentJob(Base):
    """AI content generation jobs — scheduled or on-demand."""
    __tablename__ = "content_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(
        Enum("blog_post", "resume", "email_sequence", "social_pack",
             "product_description", "seo_audit", name="job_type_enum"),
        nullable=False,
    )
    status = Column(
        Enum("pending", "running", "done", "failed", name="job_status"),
        default="pending",
    )
    input_payload = Column(Text, nullable=True)   # JSON
    output_payload = Column(Text, nullable=True)  # JSON / markdown
    subscriber_id = Column(Integer, ForeignKey("subscribers.id"), nullable=True)
    tokens_used = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class Lead(Base):
    """Captured leads from landing pages / affiliate traffic."""
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    source = Column(String(100), nullable=True)   # utm_source
    campaign = Column(String(100), nullable=True)
    referred_by_code = Column(String(16), nullable=True)  # referral code of the person who invited them
    converted = Column(Boolean, default=False)
    sequence_step = Column(Integer, default=0)    # nurture email step
    created_at = Column(DateTime(timezone=True), default=utcnow)
    last_emailed_at = Column(DateTime(timezone=True), nullable=True)


class PublishedContent(Base):
    """Blog posts auto-published to WordPress."""
    __tablename__ = "published_content"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    slug = Column(String(500), nullable=True)
    keyword = Column(String(255), nullable=True)
    wp_post_id = Column(Integer, nullable=True)
    affiliate_links_injected = Column(Integer, default=0)
    estimated_monthly_revenue = Column(Float, default=0.0)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ApiLog(Base):
    """Per-call API usage log for rate limiting and billing."""
    __tablename__ = "api_logs"

    id = Column(Integer, primary_key=True, index=True)
    subscriber_id = Column(Integer, ForeignKey("subscribers.id"), nullable=True)
    endpoint = Column(String(200), nullable=False)
    tokens_used = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    success = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    subscriber = relationship("Subscriber", back_populates="api_logs")


def create_tables():
    Base.metadata.create_all(bind=engine)

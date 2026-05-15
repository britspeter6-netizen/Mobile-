"""
Revenue analytics — tracks every dollar, projects growth, surfaces insight.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import func

from core.config import get_settings
from core.database import (
    Lead, Order, PublishedContent, RevenueEvent, SessionLocal, Subscriber,
)

settings = get_settings()


def snapshot_revenue(db=None) -> dict:
    """
    Current-month revenue breakdown across all streams.
    Returns a dict safe for JSON serialisation.
    """
    close_db = db is None
    if db is None:
        db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # ── Stripe MRR ────────────────────────────────────────────────
        active_subs = db.query(Subscriber).filter_by(status="active").all()
        plan_prices = {"starter": 29.0, "pro": 79.0, "agency": 199.0}
        mrr_stripe = sum(plan_prices.get(s.plan, 0) for s in active_subs)

        plan_counts = {"starter": 0, "pro": 0, "agency": 0}
        for s in active_subs:
            plan_counts[s.plan] = plan_counts.get(s.plan, 0) + 1

        # ── Gumroad this month ────────────────────────────────────────
        gumroad_revenue = db.query(func.sum(RevenueEvent.amount_usd)).filter(
            RevenueEvent.source == "gumroad_sale",
            RevenueEvent.recorded_at >= month_start,
        ).scalar() or 0.0

        # ── Affiliate estimate (from published content) ────────────────
        posts = db.query(PublishedContent).all()
        affiliate_estimate = sum(p.estimated_monthly_revenue for p in posts)

        # ── Total ─────────────────────────────────────────────────────
        total_mrr = mrr_stripe + gumroad_revenue + affiliate_estimate
        target    = settings.revenue_target_monthly
        progress  = min(100.0, (total_mrr / target) * 100) if target > 0 else 0.0

        # ── Leads ─────────────────────────────────────────────────────
        total_leads    = db.query(Lead).count()
        converted_leads = db.query(Lead).filter_by(converted=True).count()
        conv_rate = (converted_leads / total_leads * 100) if total_leads > 0 else 0.0

        # ── Content ───────────────────────────────────────────────────
        published_posts = db.query(PublishedContent).count()

        return {
            "timestamp":          now.isoformat(),
            "mrr":                round(total_mrr, 2),
            "target_mrr":         target,
            "progress_pct":       round(progress, 1),
            "stripe_mrr":         round(mrr_stripe, 2),
            "gumroad_month":      round(gumroad_revenue, 2),
            "affiliate_estimate": round(affiliate_estimate, 2),
            "active_subscribers": len(active_subs),
            "plan_breakdown":     plan_counts,
            "total_leads":        total_leads,
            "converted_leads":    converted_leads,
            "lead_conv_rate_pct": round(conv_rate, 1),
            "published_posts":    published_posts,
            "gap_to_target":      round(max(0, target - total_mrr), 2),
        }
    finally:
        if close_db:
            db.close()


def revenue_history(days: int = 30, db=None) -> list[dict]:
    """Daily revenue totals for the last N days."""
    close_db = db is None
    if db is None:
        db = SessionLocal()
    try:
        now   = datetime.now(timezone.utc)
        start = now - timedelta(days=days)
        events = db.query(RevenueEvent).filter(
            RevenueEvent.recorded_at >= start
        ).order_by(RevenueEvent.recorded_at).all()

        by_day: dict[str, float] = {}
        for event in events:
            day = event.recorded_at.strftime("%Y-%m-%d")
            by_day[day] = round(by_day.get(day, 0.0) + event.amount_usd, 2)

        return [{"date": d, "revenue": v} for d, v in sorted(by_day.items())]
    finally:
        if close_db:
            db.close()


def top_products(limit: int = 10, db=None) -> list[dict]:
    """Top-earning Gumroad products this month."""
    close_db = db is None
    if db is None:
        db = SessionLocal()
    try:
        now         = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        rows = (
            db.query(
                Order.product_name,
                func.count(Order.id).label("sales"),
                func.sum(Order.amount_usd).label("revenue"),
            )
            .filter(Order.created_at >= month_start)
            .group_by(Order.product_name)
            .order_by(func.sum(Order.amount_usd).desc())
            .limit(limit)
            .all()
        )
        return [
            {"product": r.product_name, "sales": r.sales,
             "revenue": round(r.revenue or 0, 2)}
            for r in rows
        ]
    finally:
        if close_db:
            db.close()


def growth_projection(months: int = 6, db=None) -> list[dict]:
    """
    Simple compound growth projection based on current MRR and
    assumed 15% MoM growth (conservative for content + SaaS combo).
    """
    snap = snapshot_revenue(db)
    current_mrr = snap["mrr"]
    growth_rate = 0.15  # 15% MoM

    projections = []
    from datetime import date
    today = date.today()
    for i in range(months + 1):
        month = today.replace(day=1)
        from dateutil.relativedelta import relativedelta
        proj_date = month + relativedelta(months=i)
        proj_mrr  = current_mrr * ((1 + growth_rate) ** i)
        projections.append({
            "month":     proj_date.strftime("%Y-%m"),
            "mrr":       round(proj_mrr, 0),
            "hits_goal": proj_mrr >= settings.revenue_target_monthly,
        })
    return projections

"""
Silent automation engine — the heartbeat of the passive income machine.
Runs on APScheduler. Every job here generates or protects revenue
with zero human involvement.

Schedule overview:
  Every 6 hours  → Publish 1 SEO blog post
  Every 12 hours → Process nurture email sequence
  Every 12 hours → Fulfil pending Gumroad orders
  Daily 9am UTC  → Generate social media content pack
  Daily midnight → Reset / analytics snapshot
  Weekly Sunday  → Keyword research + content calendar refresh
"""
import json
import logging
import random
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.config import get_settings
from core.database import SessionLocal, utcnow

settings = get_settings()
log = logging.getLogger("scheduler")


# ── Content calendar ──────────────────────────────────────────────────────────
# Seed keywords — the AI writes one article per keyword, then cycles.
# Add more to scale traffic.
CONTENT_CALENDAR = [
    ("best ai tools for small business", "software tools"),
    ("how to make money with chatgpt", "ai monetization"),
    ("passive income ideas 2025", "passive income"),
    ("best email marketing software for creators", "email marketing software"),
    ("home office setup for remote workers", "home office"),
    ("how to start a blog and make money", "blogging income"),
    ("best project management tool for freelancers", "project management tool"),
    ("ai writing tools comparison", "ai writing tool"),
    ("best vpn for privacy 2025", "vpn"),
    ("freelance accounting software review", "accounting software"),
    ("how to build a saas with no code", "no-code saas"),
    ("best web hosting for wordpress", "web hosting"),
    ("how to sell digital products online", "digital products"),
    ("email sequence that converts", "email marketing software"),
    ("linkedin growth strategy 2025", "linkedin"),
    ("how to use ai for content marketing", "ai content marketing"),
    ("course platform comparison teachable vs kajabi", "course platform"),
    ("how to automate your business with ai", "ai automation"),
    ("best tools for solopreneurs", "software tools"),
    ("how to rank on google in 2025", "seo strategy"),
]

_calendar_index = 0


def _next_keyword() -> tuple[str, str]:
    global _calendar_index
    kw, ctx = CONTENT_CALENDAR[_calendar_index % len(CONTENT_CALENDAR)]
    _calendar_index += 1
    return kw, ctx


# ── Jobs ──────────────────────────────────────────────────────────────────────

def job_publish_blog_post():
    """Generate + publish one SEO article with affiliate links."""
    from products.content_writer import generate_blog_post
    from channels.wordpress_publisher import publish_post

    keyword, affiliate_ctx = _next_keyword()
    log.info(f"[Scheduler] Generating blog post: '{keyword}'")

    result = generate_blog_post(
        keyword=keyword,
        word_count=random.choice([1200, 1500, 1800]),
        affiliate_context=f"Relevant affiliate product category: {affiliate_ctx}",
    )

    if result["status"] == "done" and result["content"]:
        # Extract title from first H1 in content
        lines = result["content"].splitlines()
        title = keyword.title()
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                break

        wp_id = publish_post(
            title=title,
            content_md=result["content"],
            keyword=keyword,
        )
        log.info(f"[Scheduler] Published WP post {wp_id} for '{keyword}'")
    else:
        log.warning(f"[Scheduler] Blog generation failed for '{keyword}'")


def job_process_email_sequences():
    """Advance nurture sequences for all leads."""
    from channels.email_sender import process_nurture_sequences
    log.info("[Scheduler] Running email nurture sequences")
    process_nurture_sequences()


def job_fulfill_gumroad_orders():
    """Deliver digital products to unfulfilled Gumroad buyers."""
    from revenue.gumroad import get_unfulfilled_orders, mark_fulfilled
    from channels.email_sender import send_gumroad_fulfillment

    PRODUCT_CONTENT = {
        "AI Mega Prompt Pack (500 prompts)": (
            "Your 500 AI prompts are attached. Top 5 to start:\n\n"
            "1. 'Act as a senior copywriter. Write a 5-email sequence for [product] targeting [audience]...'\n"
            "2. 'Analyse this keyword list and cluster by intent: [keywords]...'\n"
            "3. 'Write an SEO article outline for: [keyword]. Include 6 H2s and FAQ section...'\n"
            "4. 'You are a cold email expert. Write 3 variants for pitching [offer] to [role]...'\n"
            "5. 'Create a 30-day social media calendar for [brand] in [niche]...'\n\n"
            "Full pack: https://passiveengine.io/downloads/prompt-pack-500.pdf"
        ),
        "SEO Content Starter Kit": (
            "Your SEO Content Starter Kit includes:\n"
            "• 20 article templates (pre-structured for Google ranking)\n"
            "• Keyword research spreadsheet\n"
            "• On-page SEO checklist\n"
            "• Internal linking strategy guide\n\n"
            "Download: https://passiveengine.io/downloads/seo-content-kit.zip"
        ),
    }

    db = SessionLocal()
    try:
        orders = get_unfulfilled_orders(db)
        for order in orders:
            content = PRODUCT_CONTENT.get(
                order.product_name,
                "Your download is ready at: https://passiveengine.io/downloads"
            )
            send_gumroad_fulfillment(order.buyer_email, order.product_name, content)
            mark_fulfilled(db, order)
            log.info(f"[Scheduler] Fulfilled order {order.id} → {order.buyer_email}")
    finally:
        db.close()


def job_daily_social_content():
    """Generate social media posts for the week ahead (content buffer)."""
    from products.content_writer import generate_social_pack

    result = generate_social_pack(
        brand="PassiveEngine",
        niche="AI automation & passive income",
        platforms=["Twitter", "LinkedIn", "Instagram"],
        posts_per_platform=3,
    )
    if result["status"] == "done":
        log.info(f"[Scheduler] Social pack generated — {result['cost']:.4f} cost")
    else:
        log.warning("[Scheduler] Social pack generation failed")


def job_weekly_keyword_research():
    """Refresh the keyword pipeline with new niche research."""
    from products.content_writer import generate_keyword_cluster

    niches = [
        "AI tools for freelancers",
        "passive income online",
        "email marketing for small business",
        "productivity software 2025",
    ]
    for niche in niches:
        result = generate_keyword_cluster(niche, count=15)
        log.info(f"[Scheduler] Keywords for '{niche}': {result['status']} | "
                 f"${result['cost']:.4f}")


def job_analytics_snapshot():
    """Daily revenue snapshot logged to console / DB."""
    from automation.analytics import snapshot_revenue
    snapshot = snapshot_revenue()
    log.info(
        f"[Analytics] MRR: ${snapshot['mrr']:.0f} | "
        f"Target: ${settings.revenue_target_monthly:.0f} | "
        f"Progress: {snapshot['progress_pct']:.1f}%"
    )


# ── Scheduler bootstrap ───────────────────────────────────────────────────────

def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")

    # SEO blog posts — every 6 hours
    scheduler.add_job(
        job_publish_blog_post,
        IntervalTrigger(hours=6),
        id="publish_blog",
        replace_existing=True,
        max_instances=1,
    )

    # Email nurture — every 12 hours
    scheduler.add_job(
        job_process_email_sequences,
        IntervalTrigger(hours=12),
        id="email_sequences",
        replace_existing=True,
        max_instances=1,
    )

    # Gumroad fulfilment — every 12 hours
    scheduler.add_job(
        job_fulfill_gumroad_orders,
        IntervalTrigger(hours=12),
        id="gumroad_fulfill",
        replace_existing=True,
        max_instances=1,
    )

    # Social content — daily 9am UTC
    scheduler.add_job(
        job_daily_social_content,
        CronTrigger(hour=9, minute=0),
        id="social_content",
        replace_existing=True,
    )

    # Analytics snapshot — daily midnight UTC
    scheduler.add_job(
        job_analytics_snapshot,
        CronTrigger(hour=0, minute=0),
        id="analytics_snapshot",
        replace_existing=True,
    )

    # Keyword research — every Sunday 6am UTC
    scheduler.add_job(
        job_weekly_keyword_research,
        CronTrigger(day_of_week="sun", hour=6),
        id="keyword_research",
        replace_existing=True,
    )

    return scheduler

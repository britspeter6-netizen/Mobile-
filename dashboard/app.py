"""
FastAPI application — customer API + admin dashboard + webhooks.

Endpoints:
  GET  /                          Landing page redirect
  GET  /health                    Liveness probe
  GET  /pricing                   Plan info
  POST /leads/capture             Capture lead → start email sequence
  POST /subscribe/checkout        Create Stripe checkout session
  POST /webhooks/stripe           Stripe event handler
  POST /webhooks/gumroad          Gumroad sale handler

  — Authenticated API (X-API-Key header) —
  POST /api/v1/content/blog-post          Generate SEO article
  POST /api/v1/content/keywords           Keyword cluster
  POST /api/v1/content/resume             Resume
  POST /api/v1/content/cover-letter       Cover letter
  POST /api/v1/content/email-sequence     Email nurture sequence
  POST /api/v1/content/social-pack        Social media content pack
  POST /api/v1/content/product-description  Product copy
  POST /api/v1/research/niche             Niche analysis
  GET  /api/v1/account                    Account info + usage

  — Admin (secret header) —
  GET  /admin/snapshot                    Revenue snapshot
  GET  /admin/history                     Daily revenue history
  GET  /admin/projection                  Growth projection
  GET  /admin/top-products                Top Gumroad products
  POST /admin/trigger/blog-post           Manually trigger blog publish
  POST /admin/trigger/email-sequences     Manually trigger nurture run
"""
import json
import time
from functools import wraps
from typing import Optional

from contextlib import asynccontextmanager

from fastapi import (
    BackgroundTasks, Depends, FastAPI, Header, HTTPException,
    Request, Response,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr

from core.config import get_settings
from core.database import ApiLog, SessionLocal, Subscriber, create_tables, utcnow
from revenue.stripe_billing import (
    check_api_quota, create_checkout_session, handle_webhook_event,
    increment_api_usage, verify_webhook,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    from automation.scheduler import build_scheduler
    scheduler = build_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown(wait=False)


app = FastAPI(
    title="PassiveEngine API",
    description="AI-powered content & automation — your always-on revenue engine.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def get_subscriber(x_api_key: str = Header(None)) -> Subscriber:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    db = SessionLocal()
    try:
        sub = db.query(Subscriber).filter_by(api_key=x_api_key).first()
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid API key")
        if not check_api_quota(sub):
            raise HTTPException(
                status_code=429,
                detail=f"Monthly quota exceeded for {sub.plan} plan. Upgrade at /pricing",
            )
        return sub
    finally:
        db.close()


def get_admin(x_admin_key: str = Header(None)):
    if x_admin_key != settings.secret_key:
        raise HTTPException(status_code=403, detail="Forbidden")


def log_api_call(subscriber_id: int, endpoint: str,
                 tokens: int, latency_ms: int, success: bool):
    db = SessionLocal()
    try:
        db.add(ApiLog(
            subscriber_id=subscriber_id,
            endpoint=endpoint,
            tokens_used=tokens,
            latency_ms=latency_ms,
            success=success,
        ))
        sub = db.query(Subscriber).filter_by(id=subscriber_id).first()
        if sub:
            increment_api_usage(db, sub)
    finally:
        db.close()


# ── Public routes ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/docs")


@app.get("/health")
async def health():
    return {"status": "ok", "time": utcnow().isoformat()}


@app.get("/pricing")
async def pricing():
    return {
        "plans": [
            {
                "name":       "Starter",
                "price_usd":  29,
                "period":     "month",
                "api_calls":  500,
                "features":   ["All content endpoints", "Email support"],
            },
            {
                "name":       "Pro",
                "price_usd":  79,
                "period":     "month",
                "api_calls":  2000,
                "features":   ["All content endpoints", "Priority support", "Bulk jobs"],
            },
            {
                "name":       "Agency",
                "price_usd":  199,
                "period":     "month",
                "api_calls":  10000,
                "features":   ["All content endpoints", "White-label", "SLA", "Team seats"],
            },
        ]
    }


# ── Lead capture ──────────────────────────────────────────────────────────────

class LeadIn(BaseModel):
    email: EmailStr
    source: str = ""
    campaign: str = ""
    first_name: str = ""


@app.post("/leads/capture")
async def capture_lead(body: LeadIn):
    from automation.lead_capture import capture_lead as _capture
    result = _capture(body.email, body.source, body.campaign, body.first_name)
    return result


# ── Stripe checkout ───────────────────────────────────────────────────────────

class CheckoutIn(BaseModel):
    email: EmailStr
    plan: str = "starter"


@app.post("/subscribe/checkout")
async def checkout(body: CheckoutIn):
    if body.plan not in ("starter", "pro", "agency"):
        raise HTTPException(400, "Invalid plan")
    url = create_checkout_session(
        email=body.email,
        plan=body.plan,
        success_url=f"{settings.base_url}/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.base_url}/pricing",
    )
    return {"checkout_url": url}


# ── Webhooks ──────────────────────────────────────────────────────────────────

@app.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(request: Request):
    payload   = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = verify_webhook(payload, sig_header)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    result = handle_webhook_event(event)
    return {"received": True, "result": result}


class GumroadWebhookIn(BaseModel):
    sale_id:            Optional[str] = None
    email:              Optional[str] = None
    product_permalink:  Optional[str] = None
    product_name:       Optional[str] = None
    price:              Optional[str] = "0"


@app.post("/webhooks/gumroad", include_in_schema=False)
async def gumroad_webhook(request: Request, background_tasks: BackgroundTasks):
    form = await request.form()
    payload = dict(form)
    from revenue.gumroad import handle_sale_webhook
    result = handle_sale_webhook(payload)
    # Fulfil in background immediately
    background_tasks.add_task(_fulfill_gumroad_background)
    return {"received": True, "result": result}


def _fulfill_gumroad_background():
    from automation.scheduler import job_fulfill_gumroad_orders
    job_fulfill_gumroad_orders()


# ── Authenticated content API ─────────────────────────────────────────────────

class BlogPostIn(BaseModel):
    keyword: str
    word_count: int = 1500
    affiliate_context: str = ""


@app.post("/api/v1/content/blog-post")
async def api_blog_post(body: BlogPostIn,
                         subscriber: Subscriber = Depends(get_subscriber)):
    t0 = time.perf_counter()
    from products.content_writer import generate_blog_post
    result = generate_blog_post(
        keyword=body.keyword,
        word_count=body.word_count,
        subscriber_id=subscriber.id,
        affiliate_context=body.affiliate_context,
    )
    latency = int((time.perf_counter() - t0) * 1000)
    log_api_call(subscriber.id, "/api/v1/content/blog-post",
                 result.get("tokens", 0), latency, result["status"] == "done")
    return result


class KeywordsIn(BaseModel):
    niche: str
    count: int = 20


@app.post("/api/v1/content/keywords")
async def api_keywords(body: KeywordsIn,
                        subscriber: Subscriber = Depends(get_subscriber)):
    from products.content_writer import generate_keyword_cluster
    return generate_keyword_cluster(body.niche, body.count, subscriber.id)


class ResumeIn(BaseModel):
    job_title: str
    experience_bullets: str
    target_role: str
    industry: str


@app.post("/api/v1/content/resume")
async def api_resume(body: ResumeIn,
                      subscriber: Subscriber = Depends(get_subscriber)):
    from products.content_writer import generate_resume
    return generate_resume(
        body.job_title, body.experience_bullets,
        body.target_role, body.industry, subscriber.id,
    )


class CoverLetterIn(BaseModel):
    company: str
    role: str
    candidate_summary: str


@app.post("/api/v1/content/cover-letter")
async def api_cover_letter(body: CoverLetterIn,
                            subscriber: Subscriber = Depends(get_subscriber)):
    from products.content_writer import generate_cover_letter
    return generate_cover_letter(
        body.company, body.role, body.candidate_summary, subscriber.id
    )


class EmailSequenceIn(BaseModel):
    product: str
    pain_point: str
    steps: int = 5


@app.post("/api/v1/content/email-sequence")
async def api_email_sequence(body: EmailSequenceIn,
                               subscriber: Subscriber = Depends(get_subscriber)):
    from products.content_writer import generate_email_sequence
    return generate_email_sequence(
        body.product, body.pain_point, body.steps, subscriber.id
    )


class SocialPackIn(BaseModel):
    brand: str
    niche: str
    platforms: list[str] = ["Twitter", "LinkedIn", "Instagram"]
    posts_per_platform: int = 5


@app.post("/api/v1/content/social-pack")
async def api_social_pack(body: SocialPackIn,
                           subscriber: Subscriber = Depends(get_subscriber)):
    from products.content_writer import generate_social_pack
    return generate_social_pack(
        body.brand, body.niche, body.platforms, body.posts_per_platform, subscriber.id
    )


class ProductDescIn(BaseModel):
    product_name: str
    features: str
    target_customer: str


@app.post("/api/v1/content/product-description")
async def api_product_description(body: ProductDescIn,
                                   subscriber: Subscriber = Depends(get_subscriber)):
    from products.content_writer import generate_product_description
    return generate_product_description(
        body.product_name, body.features, body.target_customer, subscriber.id
    )


class NicheResearchIn(BaseModel):
    niche: str


@app.post("/api/v1/research/niche")
async def api_niche_research(body: NicheResearchIn,
                              subscriber: Subscriber = Depends(get_subscriber)):
    from products.content_writer import research_niche
    return research_niche(body.niche, subscriber.id)


@app.get("/api/v1/account")
async def api_account(subscriber: Subscriber = Depends(get_subscriber)):
    from revenue.stripe_billing import PLAN_LIMITS
    limit = PLAN_LIMITS.get(subscriber.plan, {}).get("api_calls", 0)
    return {
        "email":            subscriber.email,
        "plan":             subscriber.plan,
        "status":           subscriber.status,
        "api_calls_used":   subscriber.api_calls_this_month,
        "api_calls_limit":  limit,
        "api_calls_left":   max(0, limit - subscriber.api_calls_this_month),
        "member_since":     subscriber.created_at.isoformat(),
    }


# ── Admin routes ──────────────────────────────────────────────────────────────

@app.get("/admin/snapshot", dependencies=[Depends(get_admin)])
async def admin_snapshot():
    from automation.analytics import snapshot_revenue
    return snapshot_revenue()


@app.get("/admin/history", dependencies=[Depends(get_admin)])
async def admin_history(days: int = 30):
    from automation.analytics import revenue_history
    return revenue_history(days)


@app.get("/admin/projection", dependencies=[Depends(get_admin)])
async def admin_projection(months: int = 6):
    from automation.analytics import growth_projection
    return growth_projection(months)


@app.get("/admin/top-products", dependencies=[Depends(get_admin)])
async def admin_top_products():
    from automation.analytics import top_products
    return top_products()


@app.post("/admin/trigger/blog-post", dependencies=[Depends(get_admin)])
async def admin_trigger_blog(background_tasks: BackgroundTasks):
    from automation.scheduler import job_publish_blog_post
    background_tasks.add_task(job_publish_blog_post)
    return {"triggered": "blog_post"}


@app.post("/admin/trigger/email-sequences", dependencies=[Depends(get_admin)])
async def admin_trigger_email(background_tasks: BackgroundTasks):
    from automation.scheduler import job_process_email_sequences
    background_tasks.add_task(job_process_email_sequences)
    return {"triggered": "email_sequences"}

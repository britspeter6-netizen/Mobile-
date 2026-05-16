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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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

_LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PassiveEngine — AI Income Engine, Running 24/7</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    background:#0a0a0f;color:#e8e8f0;line-height:1.6}
  a{color:#7c6af7;text-decoration:none}
  .hero{text-align:center;padding:80px 20px 60px;
    background:linear-gradient(135deg,#0a0a0f 0%,#141428 100%)}
  .hero h1{font-size:clamp(2rem,5vw,3.5rem);font-weight:800;
    background:linear-gradient(90deg,#7c6af7,#a855f7);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;
    margin-bottom:20px}
  .hero p{font-size:1.2rem;color:#9090b0;max-width:600px;
    margin:0 auto 40px}
  .badge{display:inline-block;background:#1e1e3a;border:1px solid #3a3a6a;
    border-radius:20px;padding:6px 16px;font-size:.85rem;
    color:#9090b0;margin-bottom:24px}
  .cta-form{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;
    max-width:500px;margin:0 auto}
  .cta-form input{flex:1;min-width:220px;padding:14px 18px;
    border-radius:8px;border:1px solid #3a3a6a;background:#141428;
    color:#e8e8f0;font-size:1rem}
  .btn{padding:14px 28px;border-radius:8px;border:none;cursor:pointer;
    font-size:1rem;font-weight:600;transition:opacity .2s}
  .btn-primary{background:linear-gradient(135deg,#7c6af7,#a855f7);
    color:#fff}
  .btn-primary:hover{opacity:.9}
  .msg{margin-top:14px;font-size:.9rem;color:#7c6af7;min-height:22px}
  .features{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
    gap:24px;max-width:960px;margin:60px auto;padding:0 20px}
  .card{background:#141428;border:1px solid #2a2a4a;border-radius:12px;
    padding:28px}
  .card .icon{font-size:2rem;margin-bottom:12px}
  .card h3{font-size:1.1rem;margin-bottom:8px;color:#e8e8f0}
  .card p{color:#7070a0;font-size:.95rem}
  .pricing{text-align:center;padding:60px 20px;background:#0d0d1a}
  .pricing h2{font-size:2rem;margin-bottom:12px}
  .pricing p{color:#9090b0;margin-bottom:48px}
  .plans{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
    gap:24px;max-width:860px;margin:0 auto}
  .plan{background:#141428;border:1px solid #2a2a4a;border-radius:12px;
    padding:32px 24px;text-align:left}
  .plan.featured{border-color:#7c6af7;position:relative}
  .plan.featured::before{content:"Most Popular";position:absolute;top:-12px;
    left:50%;transform:translateX(-50%);background:#7c6af7;color:#fff;
    font-size:.75rem;font-weight:700;padding:3px 14px;border-radius:20px}
  .plan-name{font-size:1rem;color:#9090b0;text-transform:uppercase;
    letter-spacing:.08em}
  .plan-price{font-size:2.6rem;font-weight:800;margin:8px 0 4px}
  .plan-price span{font-size:1rem;font-weight:400;color:#7070a0}
  .plan ul{list-style:none;margin:20px 0 28px;color:#9090b0;font-size:.95rem}
  .plan ul li{padding:5px 0}
  .plan ul li::before{content:"✓  ";color:#7c6af7}
  .plan .btn{width:100%;text-align:center}
  .social-proof{max-width:800px;margin:60px auto;padding:0 20px;text-align:center}
  .social-proof h2{font-size:1.6rem;margin-bottom:32px}
  .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
    gap:20px}
  .stat{background:#141428;border:1px solid #2a2a4a;border-radius:10px;padding:20px}
  .stat .num{font-size:2rem;font-weight:800;color:#7c6af7}
  .stat .label{color:#7070a0;font-size:.85rem;margin-top:4px}
  footer{text-align:center;padding:40px 20px;color:#5050708;font-size:.85rem;
    border-top:1px solid #1a1a2e}
</style>
</head>
<body>

<section class="hero">
  <div class="badge">&#9889; AI-Powered — Zero daily maintenance</div>
  <h1>Your income engine,<br>running 24/7</h1>
  <p>PassiveEngine generates SEO content, sells digital products, and earns
     affiliate commissions — fully automated while you focus on other things.</p>
  <div class="cta-form">
    <input type="text" id="fn" placeholder="First name (optional)">
    <input type="email" id="em" placeholder="Your email address" required>
    <button class="btn btn-primary" onclick="captureLead()">Get Free AI Toolkit</button>
  </div>
  <p class="msg" id="msg"></p>
</section>

<section class="features">
  <div class="card">
    <div class="icon">&#129302;</div>
    <h3>AI Content API ($29–$199/mo)</h3>
    <p>Sell access to your content engine. Businesses pay monthly for
       AI-written blog posts, resumes, email sequences, and social packs.</p>
  </div>
  <div class="card">
    <div class="icon">&#128218;</div>
    <h3>Digital Downloads</h3>
    <p>5 pre-built products on Gumroad — prompt packs, email templates,
       resume bundles. One-time purchases, instant delivery, no inventory.</p>
  </div>
  <div class="card">
    <div class="icon">&#128181;</div>
    <h3>Affiliate Commissions</h3>
    <p>Every blog post published has monetized links injected automatically.
       10+ affiliate programs. Commissions earned while you sleep.</p>
  </div>
</section>

<section class="social-proof">
  <h2>What gets automated for you</h2>
  <div class="stats">
    <div class="stat"><div class="num">4/day</div><div class="label">SEO articles auto-published</div></div>
    <div class="stat"><div class="num">10-day</div><div class="label">Email nurture sequence</div></div>
    <div class="stat"><div class="num">10+</div><div class="label">Affiliate networks wired in</div></div>
    <div class="stat"><div class="num">3</div><div class="label">Revenue streams at once</div></div>
  </div>
</section>

<section class="pricing">
  <h2>Simple, transparent pricing</h2>
  <p>All plans include every content endpoint and full automation. Cancel any time.</p>
  <div class="plans">
    <div class="plan">
      <div class="plan-name">Starter</div>
      <div class="plan-price">$29<span>/mo</span></div>
      <ul>
        <li>500 API calls / month</li>
        <li>All content endpoints</li>
        <li>Email support</li>
      </ul>
      <button class="btn btn-primary" onclick="startTrial('starter')">Get Started</button>
    </div>
    <div class="plan featured">
      <div class="plan-name">Pro</div>
      <div class="plan-price">$79<span>/mo</span></div>
      <ul>
        <li>2,000 API calls / month</li>
        <li>All content endpoints</li>
        <li>Priority support</li>
        <li>Bulk jobs</li>
      </ul>
      <button class="btn btn-primary" onclick="startTrial('pro')">Get Started</button>
    </div>
    <div class="plan">
      <div class="plan-name">Agency</div>
      <div class="plan-price">$199<span>/mo</span></div>
      <ul>
        <li>10,000 API calls / month</li>
        <li>All content endpoints</li>
        <li>White-label</li>
        <li>Team seats + SLA</li>
      </ul>
      <button class="btn btn-primary" onclick="startTrial('agency')">Get Started</button>
    </div>
  </div>
</section>

<footer>
  <p>&copy; 2026 PassiveEngine &mdash; <a href="/docs">API Docs</a> &mdash; <a href="/pricing">Pricing JSON</a></p>
</footer>

<script>
  // Persist referral code from URL so it survives the form submission
  const params = new URLSearchParams(window.location.search);
  const ref = params.get('ref') || localStorage.getItem('pe_ref') || '';
  if (ref) localStorage.setItem('pe_ref', ref);

  async function captureLead() {
    const email = document.getElementById('em').value.trim();
    const name  = document.getElementById('fn').value.trim();
    const msg   = document.getElementById('msg');
    if (!email) { msg.textContent = 'Please enter your email.'; return; }
    msg.textContent = 'Sending…';
    try {
      const r = await fetch('/leads/capture', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({email, first_name:name,
          source:'landing_page', referral_code: localStorage.getItem('pe_ref')||''})
      });
      const d = await r.json();
      msg.textContent = d.status==='existing'
        ? 'You’re already on the list — check your inbox!'
        : '✓ Check your email for your free AI toolkit!';
    } catch(e) { msg.textContent = 'Something went wrong — try again.'; }
  }

  async function startTrial(plan) {
    const email = document.getElementById('em').value.trim();
    if (!email) {
      document.getElementById('msg').textContent = 'Enter your email above first.';
      document.getElementById('em').focus(); return;
    }
    try {
      const r = await fetch('/subscribe/checkout', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({email, plan})
      });
      const d = await r.json();
      if (d.checkout_url) window.location.href = d.checkout_url;
      else document.getElementById('msg').textContent = 'Could not start checkout — try again.';
    } catch(e) {
      document.getElementById('msg').textContent = 'Something went wrong — try again.';
    }
  }
</script>
</body>
</html>"""

_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Welcome to PassiveEngine!</title>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    background:#0a0a0f;color:#e8e8f0;display:flex;align-items:center;
    justify-content:center;min-height:100vh;text-align:center;padding:20px}
  h1{font-size:2.5rem;margin-bottom:16px;
    background:linear-gradient(90deg,#7c6af7,#a855f7);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent}
  p{color:#9090b0;max-width:480px;margin:0 auto 28px;font-size:1.05rem}
  .box{background:#141428;border:1px solid #2a2a4a;border-radius:12px;
    padding:40px;max-width:560px;width:100%}
  a.btn{display:inline-block;padding:14px 28px;border-radius:8px;
    background:linear-gradient(135deg,#7c6af7,#a855f7);color:#fff;
    font-weight:600;font-size:1rem;margin-top:8px}
</style>
</head>
<body>
<div class="box">
  <h1>&#127881; You're in!</h1>
  <p>Your PassiveEngine subscription is active. Check your email for your
     API key — it's your key to all content endpoints.</p>
  <p>Share your referral link with friends: every person who subscribes
     through your link earns you one free month.</p>
  <a class="btn" href="/docs">View API Documentation</a>
</div>
</body>
</html>"""


@app.get("/", include_in_schema=False)
async def root():
    return HTMLResponse(_LANDING_HTML)


@app.get("/success", include_in_schema=False)
async def success():
    return HTMLResponse(_SUCCESS_HTML)


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
    referral_code: str = ""


@app.post("/leads/capture")
async def capture_lead(body: LeadIn):
    from automation.lead_capture import capture_lead as _capture
    result = _capture(body.email, body.source, body.campaign,
                      body.first_name, body.referral_code)
    return result


# ── Referral program ──────────────────────────────────────────────────────────

@app.get("/referral")
async def referral_stats(subscriber: Subscriber = Depends(get_subscriber)):
    """Return the subscriber's referral link and how many credits they've earned."""
    from core.database import Lead
    db = SessionLocal()
    try:
        sub = db.query(Subscriber).filter_by(id=subscriber.id).first()
        code = sub.referral_code or ""
        link = f"{settings.base_url}/?ref={code}" if code else None
        referred = db.query(Lead).filter_by(referred_by_code=code).count() if code else 0
        converted = db.query(Lead).filter_by(
            referred_by_code=code, converted=True
        ).count() if code else 0
        return {
            "referral_link": link,
            "referral_code": code,
            "people_referred": referred,
            "people_converted": converted,
            "free_months_earned": sub.referral_credits,
        }
    finally:
        db.close()


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

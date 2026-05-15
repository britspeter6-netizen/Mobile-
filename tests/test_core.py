"""
Core unit tests — run without any live API keys.
pytest tests/
"""
import pytest
from fastapi.testclient import TestClient

from core.config import get_settings
from core.database import Base, Subscriber, create_tables, engine
from revenue.affiliate import inject_affiliate_links, estimate_monthly_revenue
from revenue.stripe_billing import generate_api_key, PLAN_LIMITS, check_api_quota
from automation.analytics import snapshot_revenue


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def fresh_db():
    """Create fresh in-memory tables for each test."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    from dashboard.app import app
    return TestClient(app)


# ── Config ────────────────────────────────────────────────────────────────────

def test_settings_loaded():
    s = get_settings()
    assert s.revenue_target_monthly == 18000.0
    assert s.ai_model == "claude-sonnet-4-6"


# ── API Key ───────────────────────────────────────────────────────────────────

def test_api_key_format():
    key = generate_api_key()
    assert key.startswith("pe_")
    assert len(key) > 20


def test_api_key_unique():
    keys = {generate_api_key() for _ in range(100)}
    assert len(keys) == 100


# ── Quota checking ────────────────────────────────────────────────────────────

def test_quota_active_subscriber():
    sub = Subscriber(
        email="test@test.com",
        plan="starter",
        status="active",
        api_calls_this_month=0,
    )
    assert check_api_quota(sub) is True


def test_quota_exceeded():
    sub = Subscriber(
        email="test@test.com",
        plan="starter",
        status="active",
        api_calls_this_month=600,  # over 500 limit
    )
    assert check_api_quota(sub) is False


def test_quota_cancelled():
    sub = Subscriber(
        email="test@test.com",
        plan="pro",
        status="cancelled",
        api_calls_this_month=0,
    )
    assert check_api_quota(sub) is False


# ── Affiliate links ───────────────────────────────────────────────────────────

def test_inject_affiliate_links_basic():
    content = "Use the best email marketing software to grow your audience."
    result, count = inject_affiliate_links(content)
    assert count == 1
    assert "[" in result and "](" in result


def test_inject_affiliate_links_max():
    content = (
        "Best email marketing software, web hosting, vpn, "
        "project management tool, accounting software, home office"
    )
    result, count = inject_affiliate_links(content, max_injections=4)
    assert count == 4


def test_inject_no_match():
    content = "The quick brown fox jumps over the lazy dog."
    result, count = inject_affiliate_links(content)
    assert count == 0
    assert result == content


def test_affiliate_revenue_estimate():
    rev = estimate_monthly_revenue(monthly_visits=1000)
    assert rev > 0


# ── Analytics ─────────────────────────────────────────────────────────────────

def test_snapshot_zero_state():
    snap = snapshot_revenue()
    assert snap["mrr"] == 0.0
    assert snap["active_subscribers"] == 0
    assert snap["progress_pct"] == 0.0
    assert "gap_to_target" in snap


# ── API endpoints (no auth) ───────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_pricing(client):
    r = client.get("/pricing")
    assert r.status_code == 200
    plans = r.json()["plans"]
    assert len(plans) == 3
    prices = {p["name"]: p["price_usd"] for p in plans}
    assert prices["Starter"] == 29
    assert prices["Pro"]     == 79
    assert prices["Agency"]  == 199


def test_lead_capture(client):
    r = client.post("/leads/capture", json={"email": "alice@example.com"})
    assert r.status_code == 200
    assert r.json()["status"] in ("new", "existing")


def test_lead_capture_duplicate(client):
    client.post("/leads/capture", json={"email": "bob@example.com"})
    r = client.post("/leads/capture", json={"email": "bob@example.com"})
    assert r.json()["status"] == "existing"


def test_api_requires_key(client):
    r = client.post("/api/v1/content/blog-post",
                    json={"keyword": "test keyword"})
    assert r.status_code == 401


def test_api_invalid_key(client):
    r = client.post("/api/v1/content/blog-post",
                    json={"keyword": "test"},
                    headers={"X-API-Key": "pe_invalid"})
    assert r.status_code == 401

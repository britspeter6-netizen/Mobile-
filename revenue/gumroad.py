"""
Gumroad digital product sales integration.
Receives webhooks on sale, auto-fulfils by emailing the deliverable.
"""
import hashlib
import hmac
import json
from typing import Optional

import httpx

from core.config import get_settings
from core.database import Order, RevenueEvent, SessionLocal, Subscriber, utcnow

settings = get_settings()

GUMROAD_API = "https://api.gumroad.com/v2"

DIGITAL_PRODUCTS = {
    "ai-prompt-pack":      {"name": "AI Mega Prompt Pack (500 prompts)", "price": 27.0},
    "seo-content-kit":     {"name": "SEO Content Starter Kit",           "price": 47.0},
    "email-swipe-vault":   {"name": "Email Swipe Vault (200 templates)", "price": 37.0},
    "resume-template-pro": {"name": "ATS Resume Template Pro Bundle",    "price": 19.0},
    "social-media-os":     {"name": "Social Media OS (Notion template)", "price": 29.0},
}


def handle_sale_webhook(payload: dict) -> str:
    """
    Called by the FastAPI webhook endpoint when Gumroad fires a sale event.
    Records revenue and queues fulfilment.
    """
    db = SessionLocal()
    try:
        sale_id     = payload.get("sale_id", "")
        email       = payload.get("email", "")
        product_id  = payload.get("product_permalink", "")
        amount_str  = payload.get("price", "0")
        amount_usd  = float(amount_str) / 100  # Gumroad sends cents

        # Idempotency — skip duplicates
        existing = db.query(Order).filter_by(gumroad_sale_id=sale_id).first()
        if existing:
            return f"duplicate:{sale_id}"

        product_info = DIGITAL_PRODUCTS.get(product_id, {
            "name": payload.get("product_name", "Digital Product"),
            "price": amount_usd,
        })

        order = Order(
            gumroad_sale_id=sale_id,
            product_name=product_info["name"],
            amount_usd=amount_usd,
            buyer_email=email,
            fulfilled=False,
        )
        db.add(order)

        rev = RevenueEvent(
            source="gumroad_sale",
            amount_usd=amount_usd,
            description=f"Gumroad: {product_info['name']}",
            external_id=sale_id,
        )
        db.add(rev)
        db.commit()

        # Fulfilment is handled by the scheduler / background task
        return f"ok:{sale_id}:{email}"
    finally:
        db.close()


def get_unfulfilled_orders(db) -> list:
    return db.query(Order).filter_by(fulfilled=False).all()


def mark_fulfilled(db, order: Order):
    order.fulfilled = True
    db.commit()


def list_products() -> list[dict]:
    """Fetch product list from Gumroad API."""
    if not settings.gumroad_access_token:
        return list(DIGITAL_PRODUCTS.values())
    with httpx.Client() as client:
        resp = client.get(
            f"{GUMROAD_API}/products",
            headers={"Authorization": f"Bearer {settings.gumroad_access_token}"},
        )
        resp.raise_for_status()
        return resp.json().get("products", [])


def create_product(name: str, description: str, price_cents: int,
                   file_url: str) -> Optional[str]:
    """Programmatically create a Gumroad product. Returns product permalink."""
    if not settings.gumroad_access_token:
        print("[Gumroad] No token — skipping product creation")
        return None
    with httpx.Client() as client:
        resp = client.post(
            f"{GUMROAD_API}/products",
            headers={"Authorization": f"Bearer {settings.gumroad_access_token}"},
            data={
                "name": name,
                "description": description,
                "price": price_cents,
                "url": file_url,
            },
        )
        resp.raise_for_status()
        return resp.json().get("product", {}).get("permalink")

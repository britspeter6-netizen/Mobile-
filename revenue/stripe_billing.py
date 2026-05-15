"""
Stripe subscription management.
Handles checkout, webhooks, and plan enforcement.
"""
import hashlib
import hmac
import json
import os
import secrets
from typing import Optional

import stripe

from core.config import get_settings
from core.database import RevenueEvent, Subscriber, SessionLocal, utcnow

settings = get_settings()
stripe.api_key = settings.stripe_secret_key

PLAN_LIMITS = {
    "starter": {"api_calls": 500,  "price_id": settings.stripe_price_starter},
    "pro":     {"api_calls": 2000, "price_id": settings.stripe_price_pro},
    "agency":  {"api_calls": 10000,"price_id": settings.stripe_price_agency},
}

PLAN_PRICES = {
    "starter": 29.0,
    "pro":     79.0,
    "agency":  199.0,
}


def generate_api_key() -> str:
    return "pe_" + secrets.token_urlsafe(40)


def create_checkout_session(email: str, plan: str, success_url: str,
                             cancel_url: str) -> str:
    """Return Stripe hosted checkout URL for the given plan."""
    price_id = PLAN_LIMITS[plan]["price_id"]
    session = stripe.checkout.Session.create(
        customer_email=email,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"plan": plan},
    )
    return session.url


def create_customer_portal(stripe_customer_id: str, return_url: str) -> str:
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=return_url,
    )
    return session.url


def verify_webhook(payload: bytes, sig_header: str) -> dict:
    """Verify Stripe signature and return parsed event dict."""
    event = stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )
    return event


def handle_webhook_event(event: dict) -> Optional[str]:
    """
    Process a verified Stripe webhook.
    Returns a short status string for logging.
    """
    db = SessionLocal()
    try:
        etype = event["type"]
        data = event["data"]["object"]

        if etype == "checkout.session.completed":
            email = data.get("customer_email")
            customer_id = data.get("customer")
            sub_id = data.get("subscription")
            plan = data.get("metadata", {}).get("plan", "starter")
            _upsert_subscriber(db, email, customer_id, sub_id, plan, "active")
            _record_revenue(db, "stripe_subscription",
                            PLAN_PRICES[plan], f"New {plan} sub: {email}", sub_id)
            return f"checkout.completed:{email}:{plan}"

        if etype == "invoice.paid":
            sub_id = data.get("subscription")
            amount = data.get("amount_paid", 0) / 100
            sub = db.query(Subscriber).filter_by(
                stripe_subscription_id=sub_id
            ).first()
            if sub:
                sub.status = "active"
                sub.renewed_at = utcnow()
                sub.api_calls_this_month = 0  # reset monthly quota
                db.commit()
            _record_revenue(db, "stripe_subscription", amount,
                            f"Renewal {sub_id}", data.get("id"))
            return f"invoice.paid:{sub_id}:${amount}"

        if etype in ("customer.subscription.deleted",
                     "customer.subscription.paused"):
            sub_id = data.get("id")
            sub = db.query(Subscriber).filter_by(
                stripe_subscription_id=sub_id
            ).first()
            if sub:
                sub.status = "cancelled"
                db.commit()
            return f"subscription.{etype.split('.')[-1]}:{sub_id}"

        if etype == "invoice.payment_failed":
            sub_id = data.get("subscription")
            sub = db.query(Subscriber).filter_by(
                stripe_subscription_id=sub_id
            ).first()
            if sub:
                sub.status = "past_due"
                db.commit()
            return f"payment.failed:{sub_id}"

        return f"unhandled:{etype}"
    finally:
        db.close()


def _upsert_subscriber(db, email, customer_id, sub_id, plan, status):
    sub = db.query(Subscriber).filter_by(email=email).first()
    if not sub:
        sub = Subscriber(email=email, api_key=generate_api_key())
        db.add(sub)
    sub.stripe_customer_id = customer_id
    sub.stripe_subscription_id = sub_id
    sub.plan = plan
    sub.status = status
    db.commit()
    return sub


def _record_revenue(db, source, amount, description, external_id=None):
    event = RevenueEvent(
        source=source,
        amount_usd=amount,
        description=description,
        external_id=external_id,
    )
    db.add(event)
    db.commit()


def check_api_quota(subscriber: Subscriber) -> bool:
    """Return True if subscriber has remaining API quota."""
    if subscriber.status != "active":
        return False
    limit = PLAN_LIMITS.get(subscriber.plan, {}).get("api_calls", 0)
    return subscriber.api_calls_this_month < limit


def increment_api_usage(db, subscriber: Subscriber):
    subscriber.api_calls_this_month += 1
    db.commit()

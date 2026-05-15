"""
Central configuration — all secrets loaded from environment variables.
Copy .env.example to .env and fill in values before running.
"""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────
    app_name: str = "PassiveEngine"
    environment: str = "production"
    secret_key: str = os.urandom(32).hex()
    base_url: str = "http://localhost:8000"

    # ── Database ─────────────────────────────────────────────────────
    database_url: str = "sqlite:///./passive_engine.db"

    # ── AI Providers ─────────────────────────────────────────────────
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"          # primary model
    ai_fallback_model: str = "gpt-4o-mini"        # fallback if quota hit
    ai_max_tokens: int = 4096

    # ── Stripe ───────────────────────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""    # e.g. price_xxx  $29/mo
    stripe_price_pro: str = ""        # $79/mo
    stripe_price_agency: str = ""     # $199/mo

    # ── Gumroad ──────────────────────────────────────────────────────
    gumroad_access_token: str = ""
    gumroad_seller_id: str = ""

    # ── Email (SMTP or Resend) ────────────────────────────────────────
    smtp_host: str = "smtp.resend.com"
    smtp_port: int = 587
    smtp_user: str = "resend"
    smtp_password: str = ""           # Resend API key
    from_email: str = "hello@yourdomain.com"
    from_name: str = "PassiveEngine"

    # ── WordPress Auto-Publisher ──────────────────────────────────────
    wp_url: str = ""                  # https://yourblog.com
    wp_username: str = ""
    wp_app_password: str = ""

    # ── Social / Twitter ─────────────────────────────────────────────
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_secret: str = ""

    # ── Affiliate ────────────────────────────────────────────────────
    amazon_associate_tag: str = ""
    clickbank_affiliate_id: str = ""

    # ── Analytics ────────────────────────────────────────────────────
    revenue_target_monthly: float = 18000.0

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()

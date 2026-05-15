"""
Affiliate link manager.
Injects monetised links into AI-generated content before publishing.
"""
import re
from typing import Optional
from core.config import get_settings

settings = get_settings()

# ── Link catalogue ────────────────────────────────────────────────────────────
# Map keyword patterns → affiliate URLs
# Add/edit as needed — these are illustrative structures.
AFFILIATE_LINKS: dict[str, dict] = {
    # Software / SaaS
    "email marketing software": {
        "url":      "https://convertkit.com/?lmref=YOUR_REF",
        "anchor":   "ConvertKit (best for creators)",
        "network":  "ConvertKit",
        "commission": "30% recurring",
    },
    "web hosting": {
        "url":      f"https://www.siteground.com/index.htm?afcode=YOUR_CODE",
        "anchor":   "SiteGround (fast & reliable)",
        "network":  "SiteGround",
        "commission": "$50-$100/sale",
    },
    "project management tool": {
        "url":      "https://monday.com/?r=YOUR_REF",
        "anchor":   "Monday.com",
        "network":  "Monday",
        "commission": "~$100/sale",
    },
    "vpn": {
        "url":      "https://nordvpn.com/YOUR_REF",
        "anchor":   "NordVPN",
        "network":  "NordVPN",
        "commission": "40% recurring",
    },
    "accounting software": {
        "url":      "https://quickbooks.intuit.com/partners/YOUR_REF",
        "anchor":   "QuickBooks",
        "network":  "Intuit",
        "commission": "$50-$200/sale",
    },
    # Amazon product categories (uses tag parameter)
    "laptop": {
        "url":      f"https://amazon.com/s?k=best+laptops&tag={settings.amazon_associate_tag}",
        "anchor":   "top-rated laptops on Amazon",
        "network":  "Amazon Associates",
        "commission": "2.5%",
    },
    "home office": {
        "url":      f"https://amazon.com/s?k=home+office+setup&tag={settings.amazon_associate_tag}",
        "anchor":   "home office essentials",
        "network":  "Amazon Associates",
        "commission": "4%",
    },
    "course platform": {
        "url":      "https://teachable.com/?via=YOUR_REF",
        "anchor":   "Teachable (top course platform)",
        "network":  "Teachable",
        "commission": "30% recurring",
    },
    "ai writing tool": {
        "url":      "https://jasper.ai?fpr=YOUR_REF",
        "anchor":   "Jasper AI",
        "network":  "Jasper",
        "commission": "25% recurring",
    },
}


def inject_affiliate_links(content: str, max_injections: int = 4) -> tuple[str, int]:
    """
    Scan markdown content for keyword matches and hyperlink them.
    Returns (modified_content, injection_count).
    Case-insensitive, replaces first occurrence only per keyword.
    """
    injected = 0
    for keyword, link_data in AFFILIATE_LINKS.items():
        if injected >= max_injections:
            break
        pattern = re.compile(r'\b' + re.escape(keyword) + r'\b', re.IGNORECASE)
        if pattern.search(content):
            replacement = f'[{link_data["anchor"]}]({link_data["url"]})'
            content, count = pattern.subn(replacement, content, count=1)
            if count:
                injected += 1
    return content, injected


def get_link_for_keyword(keyword: str) -> Optional[dict]:
    kw = keyword.lower().strip()
    return AFFILIATE_LINKS.get(kw)


def estimate_monthly_revenue(monthly_visits: int, ctr: float = 0.03,
                              avg_commission: float = 45.0,
                              conversion_rate: float = 0.02) -> float:
    """
    Rough affiliate revenue estimate.
    Default: 3% CTR → 2% purchase conversion → $45 avg commission.
    """
    clicks = monthly_visits * ctr
    sales  = clicks * conversion_rate
    return round(sales * avg_commission, 2)

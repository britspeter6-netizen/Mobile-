"""
WordPress REST API publisher.
Generates SEO article → injects affiliate links → publishes to WordPress.
"""
import json
import re
from datetime import datetime, timezone
from typing import Optional

import httpx

from core.config import get_settings
from core.database import PublishedContent, SessionLocal, utcnow
from revenue.affiliate import inject_affiliate_links, estimate_monthly_revenue

settings = get_settings()


def _wp_headers() -> dict:
    import base64
    creds = f"{settings.wp_username}:{settings.wp_app_password}"
    token = base64.b64encode(creds.encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def _markdown_to_html(md: str) -> str:
    """
    Lightweight markdown → HTML conversion (no heavy deps).
    Handles headings, bold, links, paragraphs.
    """
    html = md
    # Headings
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$',  r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$',   r'<h1>\1</h1>', html, flags=re.MULTILINE)
    # Bold / italic
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*',     r'<em>\1</em>', html)
    # Links
    html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
    # Bullet lists
    html = re.sub(r'^[-*] (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'(<li>.*?</li>\n?)+', lambda m: f'<ul>{m.group()}</ul>', html, flags=re.DOTALL)
    # Paragraphs
    parts = re.split(r'\n{2,}', html)
    parts = [
        p if re.match(r'^<(h[1-6]|ul|ol|li)', p.strip()) else f'<p>{p.strip()}</p>'
        for p in parts if p.strip()
    ]
    return "\n".join(parts)


def extract_title_and_meta(content: str) -> tuple[str, str, str]:
    """Pull title and meta description from AI-generated markdown."""
    title = ""
    meta  = ""
    body  = content

    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            lines.pop(i)
            break

    for i, line in enumerate(lines):
        if "meta description" in line.lower() and i + 1 < len(lines):
            meta = lines[i + 1].strip().lstrip(">").strip()
            lines.pop(i + 1)
            lines.pop(i)
            break

    body = "\n".join(lines)
    return title, meta, body


def publish_post(
    title: str,
    content_md: str,
    keyword: str,
    status: str = "publish",
    categories: Optional[list[int]] = None,
    tags: Optional[list[int]] = None,
) -> Optional[int]:
    """
    Publish a post to WordPress. Returns WP post ID on success.
    """
    if not settings.wp_url:
        print("[WordPress] WP_URL not set — skipping publish")
        return None

    # Inject affiliate links before converting to HTML
    monetised_md, link_count = inject_affiliate_links(content_md)

    html_content = _markdown_to_html(monetised_md)

    payload = {
        "title":   title,
        "content": html_content,
        "status":  status,
        "slug":    re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-'),
    }
    if categories:
        payload["categories"] = categories
    if tags:
        payload["tags"] = tags

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{settings.wp_url}/wp-json/wp/v2/posts",
            headers=_wp_headers(),
            json=payload,
        )
        resp.raise_for_status()
        post_data = resp.json()
        wp_id = post_data["id"]
        slug  = post_data.get("slug", "")

    # Record in DB
    db = SessionLocal()
    try:
        rec = PublishedContent(
            title=title,
            slug=slug,
            keyword=keyword,
            wp_post_id=wp_id,
            affiliate_links_injected=link_count,
            estimated_monthly_revenue=estimate_monthly_revenue(500),
            published_at=utcnow(),
        )
        db.add(rec)
        db.commit()
    finally:
        db.close()

    print(f"[WordPress] Published '{title}' (ID {wp_id}) | {link_count} affiliate links")
    return wp_id


def get_published_posts(db) -> list:
    return db.query(PublishedContent).order_by(PublishedContent.published_at.desc()).all()

"""
Email delivery via SMTP (Resend / SendGrid / any SMTP).
Handles transactional emails, lead nurture sequences, and fulfilment.
"""
import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from core.config import get_settings
from core.database import Lead, SessionLocal, utcnow

settings = get_settings()

# ── Nurture sequence ──────────────────────────────────────────────────────────
# 5-step automated sequence sent to every new lead.
NURTURE_SEQUENCE = [
    {
        "step": 0,
        "subject": "Here's your free AI toolkit 🛠️",
        "delay_days": 0,
        "body_template": """Hi there,

Thanks for signing up. Here's your free AI productivity toolkit — 20 prompts
that save founders 10+ hours a week.

[Download Free Prompt Pack] → {{cta_url}}

Talk soon,
{{sender_name}}
""",
    },
    {
        "step": 1,
        "subject": "How I generate $18k/mo with 2 hours of work",
        "delay_days": 2,
        "body_template": """Quick story.

Six months ago I was grinding 60-hour weeks. Now I work 2 hours a day
because every task I used to do manually runs on autopilot with AI.

The secret? A backend that never sleeps.

Tomorrow I'll show you the exact stack.

{{sender_name}}
""",
    },
    {
        "step": 2,
        "subject": "The 3 revenue streams that compound quietly",
        "delay_days": 4,
        "body_template": """Here are the 3 streams I run on autopilot:

1. SaaS API subscriptions ($29–$199/mo) — set up once, billed forever
2. Affiliate content sites — AI writes, I publish, Google sends traffic
3. Digital products on Gumroad — sell 24/7 with zero fulfilment work

Each one is boring. Together they're $18k/mo.

Want the backend blueprint?

→ [Get PassiveEngine Pro] ({{upgrade_url}})

{{sender_name}}
""",
    },
    {
        "step": 3,
        "subject": "Social proof (real numbers, no fluff)",
        "delay_days": 7,
        "body_template": """Numbers from last month:

• 47 new API subscribers → $3,713 MRR added
• 12 blog posts published → 8,200 new organic visits
• 31 Gumroad sales → $1,147
• Affiliate commissions → $2,890

Total: $7,750 in new MRR — from a system I didn't touch for 18 days.

The system is for sale.

→ [See plans] ({{upgrade_url}})

{{sender_name}}
""",
    },
    {
        "step": 4,
        "subject": "Last chance — offer closes tonight",
        "delay_days": 10,
        "body_template": """This is the final email in this sequence.

If passive income from AI automation sounds good to you,
the door is open — but not forever.

→ [Start free trial] ({{upgrade_url}})

If not, no worries. I'll keep sending useful stuff.

{{sender_name}}
""",
    },
]


def _render(template: str, context: dict) -> str:
    result = template
    for key, val in context.items():
        result = result.replace("{{" + key + "}}", str(val))
    return result


def _send_smtp(to_email: str, subject: str, body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{settings.from_name} <{settings.from_email}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.from_email, to_email, msg.as_string())


def send_transactional(to_email: str, subject: str, body: str):
    """Send a one-off transactional email."""
    try:
        _send_smtp(to_email, subject, body)
        print(f"[Email] Sent '{subject}' → {to_email}")
    except Exception as exc:
        print(f"[Email] Failed to send to {to_email}: {exc}")


def send_api_key(to_email: str, api_key: str, plan: str):
    body = f"""Welcome to PassiveEngine!

Your API key: {api_key}

Plan: {plan.capitalize()}

Quick start:
  curl -H "X-API-Key: {api_key}" \\
       -H "Content-Type: application/json" \\
       -d '{{"keyword": "best productivity apps", "word_count": 1200}}' \\
       {settings.base_url}/api/v1/content/blog-post

Docs: {settings.base_url}/docs

Questions? Reply to this email.

The PassiveEngine team
"""
    send_transactional(to_email, "Your PassiveEngine API Key", body)


def send_gumroad_fulfillment(to_email: str, product_name: str,
                              download_content: str):
    body = f"""Thanks for your purchase!

Product: {product_name}

Your download is below:

{'─' * 60}
{download_content[:2000]}
{'─' * 60}

If you have questions, reply to this email.

Enjoy,
The PassiveEngine team
"""
    send_transactional(to_email, f"Your {product_name} — Download Inside", body)


def add_lead_and_start_sequence(email: str, source: str = "",
                                 campaign: str = "") -> Lead:
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter_by(email=email).first()
        if not lead:
            lead = Lead(email=email, source=source, campaign=campaign, sequence_step=0)
            db.add(lead)
            db.commit()
            # Send step 0 immediately
            _send_sequence_step(lead, 0)
        return lead
    finally:
        db.close()


def process_nurture_sequences():
    """
    Called by scheduler. Sends the next step to leads that are due.
    """
    from datetime import timedelta

    db = SessionLocal()
    try:
        leads = db.query(Lead).filter(Lead.converted == False).all()
        sent_count = 0

        for lead in leads:
            step_idx = lead.sequence_step
            if step_idx >= len(NURTURE_SEQUENCE):
                continue

            step = NURTURE_SEQUENCE[step_idx]
            delay_days = step["delay_days"]

            if lead.last_emailed_at is None:
                due = True
            else:
                from datetime import timezone
                last = lead.last_emailed_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                due = (utcnow() - last).days >= delay_days

            if due:
                _send_sequence_step(lead, step_idx)
                lead.sequence_step += 1
                lead.last_emailed_at = utcnow()
                db.commit()
                sent_count += 1

        print(f"[Email] Nurture run: {sent_count} emails sent to {len(leads)} leads")
    finally:
        db.close()


def _send_sequence_step(lead: Lead, step_idx: int):
    if step_idx >= len(NURTURE_SEQUENCE):
        return
    step = NURTURE_SEQUENCE[step_idx]
    body = _render(step["body_template"], {
        "cta_url":     f"{settings.base_url}/download/free-prompts",
        "upgrade_url": f"{settings.base_url}/pricing",
        "sender_name": settings.from_name,
    })
    send_transactional(lead.email, step["subject"], body)

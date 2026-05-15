"""
Lead capture — ingest from landing page forms, affiliate traffic, or API.
Immediately starts the 5-step nurture email sequence.
"""
from core.database import Lead, SessionLocal, utcnow
from channels.email_sender import add_lead_and_start_sequence


def capture_lead(email: str, source: str = "", campaign: str = "",
                 first_name: str = "") -> dict:
    """
    Idempotent lead capture.
    Returns status and whether this is a new lead.
    """
    db = SessionLocal()
    try:
        existing = db.query(Lead).filter_by(email=email).first()
        if existing:
            return {"status": "existing", "lead_id": existing.id}

        lead = add_lead_and_start_sequence(email, source, campaign)
        return {"status": "new", "lead_id": lead.id}
    finally:
        db.close()


def mark_lead_converted(email: str, plan: str = "starter"):
    db = SessionLocal()
    try:
        lead = db.query(Lead).filter_by(email=email).first()
        if lead:
            lead.converted = True
            db.commit()
    finally:
        db.close()


def lead_stats() -> dict:
    db = SessionLocal()
    try:
        total     = db.query(Lead).count()
        converted = db.query(Lead).filter_by(converted=True).count()
        return {
            "total":     total,
            "converted": converted,
            "rate_pct":  round((converted / total * 100) if total else 0, 1),
        }
    finally:
        db.close()

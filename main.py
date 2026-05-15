"""
Entry point.

  python main.py           → runs FastAPI server (prod)
  python main.py --dev     → runs with uvicorn reload
  python main.py --migrate → only runs DB migrations
  python main.py --test    → runs a quick smoke test
"""
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)

from core.database import create_tables


def main():
    args = set(sys.argv[1:])

    if "--migrate" in args:
        create_tables()
        print("[main] DB tables created.")
        return

    if "--test" in args:
        _smoke_test()
        return

    create_tables()

    import uvicorn
    reload = "--dev" in args
    uvicorn.run(
        "dashboard.app:app",
        host="0.0.0.0",
        port=8000,
        reload=reload,
        log_level="info",
    )


def _smoke_test():
    """Quick sanity check — no live API keys required."""
    print("[Smoke] Testing DB layer…")
    from core.database import SessionLocal, Subscriber
    db = SessionLocal()
    count = db.query(Subscriber).count()
    db.close()
    print(f"[Smoke] Subscribers in DB: {count}")

    print("[Smoke] Testing affiliate link injection…")
    from revenue.affiliate import inject_affiliate_links
    sample = "Use the best email marketing software to grow your list."
    result, n = inject_affiliate_links(sample)
    print(f"[Smoke] Injected {n} links: {result}")

    print("[Smoke] Testing analytics snapshot…")
    from automation.analytics import snapshot_revenue
    snap = snapshot_revenue()
    print(f"[Smoke] Snapshot: {snap}")

    print("[Smoke] All checks passed.")


if __name__ == "__main__":
    main()

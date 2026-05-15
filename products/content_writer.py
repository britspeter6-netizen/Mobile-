"""
AI-powered content writing products delivered via API.
Covers: blog posts, resumes, email sequences, social packs, product descriptions.
"""
import json
from datetime import datetime, timezone

from ai.content_engine import ContentEngine
from ai.prompt_library import (
    seo_blog_post, keyword_cluster, resume_writer, cover_letter,
    email_sequence, cold_email, social_media_pack, linkedin_post,
    product_description, business_plan_section, niche_research,
)
from core.database import ContentJob, SessionLocal, utcnow


engine = ContentEngine()


def _run_job(db, job: ContentJob, prompt, use_cheap: bool = False):
    job.status = "running"
    db.commit()
    try:
        result = engine.cheap_generate(prompt) if use_cheap else engine.generate(prompt)
        job.status = "done"
        job.output_payload = result.text
        job.tokens_used = result.total_tokens
        job.cost_usd = result.cost_usd
        job.completed_at = utcnow()
    except Exception as exc:
        job.status = "failed"
        job.output_payload = json.dumps({"error": str(exc)})
    db.commit()
    return job


def generate_blog_post(keyword: str, word_count: int = 1500,
                        subscriber_id: int = None,
                        affiliate_context: str = "") -> dict:
    db = SessionLocal()
    try:
        prompt = seo_blog_post(keyword, word_count, affiliate_context)
        job = ContentJob(
            job_type="blog_post",
            input_payload=json.dumps({"keyword": keyword, "word_count": word_count}),
            subscriber_id=subscriber_id,
        )
        db.add(job)
        db.commit()
        _run_job(db, job, prompt)
        return {
            "job_id":  job.id,
            "status":  job.status,
            "content": job.output_payload,
            "tokens":  job.tokens_used,
            "cost":    job.cost_usd,
        }
    finally:
        db.close()


def generate_keyword_cluster(niche: str, count: int = 20,
                              subscriber_id: int = None) -> dict:
    db = SessionLocal()
    try:
        prompt = keyword_cluster(niche, count)
        job = ContentJob(
            job_type="seo_audit",
            input_payload=json.dumps({"niche": niche, "count": count}),
            subscriber_id=subscriber_id,
        )
        db.add(job)
        db.commit()
        _run_job(db, job, prompt, use_cheap=True)
        parsed = None
        if job.status == "done":
            try:
                parsed = json.loads(job.output_payload)
            except Exception:
                parsed = job.output_payload
        return {
            "job_id":    job.id,
            "status":    job.status,
            "keywords":  parsed,
            "cost":      job.cost_usd,
        }
    finally:
        db.close()


def generate_resume(job_title: str, experience_bullets: str,
                    target_role: str, industry: str,
                    subscriber_id: int = None) -> dict:
    db = SessionLocal()
    try:
        prompt = resume_writer(job_title, experience_bullets, target_role, industry)
        job = ContentJob(
            job_type="resume",
            input_payload=json.dumps({
                "job_title": job_title, "target_role": target_role,
                "industry": industry,
            }),
            subscriber_id=subscriber_id,
        )
        db.add(job)
        db.commit()
        _run_job(db, job, prompt)
        return {
            "job_id":  job.id,
            "status":  job.status,
            "resume":  job.output_payload,
            "cost":    job.cost_usd,
        }
    finally:
        db.close()


def generate_cover_letter(company: str, role: str, candidate_summary: str,
                           subscriber_id: int = None) -> dict:
    db = SessionLocal()
    try:
        prompt = cover_letter(company, role, candidate_summary)
        job = ContentJob(
            job_type="resume",
            input_payload=json.dumps({"company": company, "role": role}),
            subscriber_id=subscriber_id,
        )
        db.add(job)
        db.commit()
        _run_job(db, job, prompt)
        return {
            "job_id":       job.id,
            "status":       job.status,
            "cover_letter": job.output_payload,
            "cost":         job.cost_usd,
        }
    finally:
        db.close()


def generate_email_sequence(product: str, pain_point: str,
                             steps: int = 5,
                             subscriber_id: int = None) -> dict:
    db = SessionLocal()
    try:
        prompt = email_sequence(product, pain_point, steps)
        job = ContentJob(
            job_type="email_sequence",
            input_payload=json.dumps({
                "product": product, "pain_point": pain_point, "steps": steps
            }),
            subscriber_id=subscriber_id,
        )
        db.add(job)
        db.commit()
        _run_job(db, job, prompt)
        parsed = None
        if job.status == "done":
            try:
                parsed = json.loads(job.output_payload)
            except Exception:
                parsed = job.output_payload
        return {
            "job_id":    job.id,
            "status":    job.status,
            "sequence":  parsed,
            "cost":      job.cost_usd,
        }
    finally:
        db.close()


def generate_social_pack(brand: str, niche: str,
                          platforms: list[str], posts_per_platform: int = 5,
                          subscriber_id: int = None) -> dict:
    db = SessionLocal()
    try:
        prompt = social_media_pack(brand, niche, platforms, posts_per_platform)
        job = ContentJob(
            job_type="social_pack",
            input_payload=json.dumps({
                "brand": brand, "niche": niche, "platforms": platforms
            }),
            subscriber_id=subscriber_id,
        )
        db.add(job)
        db.commit()
        _run_job(db, job, prompt)
        parsed = None
        if job.status == "done":
            try:
                parsed = json.loads(job.output_payload)
            except Exception:
                parsed = job.output_payload
        return {
            "job_id": job.id,
            "status": job.status,
            "posts":  parsed,
            "cost":   job.cost_usd,
        }
    finally:
        db.close()


def generate_product_description(product_name: str, features: str,
                                  target_customer: str,
                                  subscriber_id: int = None) -> dict:
    db = SessionLocal()
    try:
        prompt = product_description(product_name, features, target_customer)
        job = ContentJob(
            job_type="product_description",
            input_payload=json.dumps({
                "product_name": product_name,
                "target_customer": target_customer,
            }),
            subscriber_id=subscriber_id,
        )
        db.add(job)
        db.commit()
        _run_job(db, job, prompt)
        return {
            "job_id":      job.id,
            "status":      job.status,
            "description": job.output_payload,
            "cost":        job.cost_usd,
        }
    finally:
        db.close()


def research_niche(niche: str, subscriber_id: int = None) -> dict:
    db = SessionLocal()
    try:
        prompt = niche_research(niche)
        job = ContentJob(
            job_type="seo_audit",
            input_payload=json.dumps({"niche": niche}),
            subscriber_id=subscriber_id,
        )
        db.add(job)
        db.commit()
        _run_job(db, job, prompt, use_cheap=True)
        parsed = None
        if job.status == "done":
            try:
                parsed = json.loads(job.output_payload)
            except Exception:
                parsed = job.output_payload
        return {
            "job_id":   job.id,
            "status":   job.status,
            "research": parsed,
            "cost":     job.cost_usd,
        }
    finally:
        db.close()

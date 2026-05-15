"""
Battle-tested prompt templates for every product.
Each returns a fully-formed system+user prompt pair.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Prompt:
    system: str
    user: str


# ── Blog / SEO ────────────────────────────────────────────────────────────────

def seo_blog_post(keyword: str, word_count: int = 1500,
                  affiliate_context: str = "") -> Prompt:
    return Prompt(
        system=(
            "You are an expert SEO content writer who specialises in writing "
            "long-form, deeply researched articles that rank on Google's first page. "
            "You write in a natural, helpful voice — no fluff, no filler. "
            "Every section answers a real question. Include H2/H3 headings, "
            "a meta description (155 chars), and a short intro that hooks skimmers."
        ),
        user=(
            f"Write a comprehensive {word_count}-word SEO article targeting the keyword: "
            f'"{keyword}".\n\n'
            f"Structure:\n"
            f"1. SEO title (60 chars max, include keyword)\n"
            f"2. Meta description (155 chars)\n"
            f"3. Introduction (hook + keyword in first 100 words)\n"
            f"4. 5-7 H2 sections with H3 subsections where needed\n"
            f"5. FAQ section (5 questions, schema-ready)\n"
            f"6. Conclusion with CTA\n\n"
            f"{('Affiliate context: ' + affiliate_context) if affiliate_context else ''}\n"
            f"Return valid markdown."
        ),
    )


def keyword_cluster(niche: str, count: int = 20) -> Prompt:
    return Prompt(
        system=(
            "You are an SEO strategist. You think in keyword clusters, "
            "search intent, and commercial value. You only suggest keywords "
            "with real search volume and buyer intent."
        ),
        user=(
            f"Generate {count} high-value, low-competition keywords for the niche: '{niche}'.\n\n"
            "For each keyword output:\n"
            "- keyword\n- estimated monthly searches (US)\n- intent (informational/commercial/transactional)\n"
            "- suggested article angle\n- monetisation method (affiliate/SaaS/ads)\n\n"
            "Return as JSON array."
        ),
    )


# ── Resume & Career ───────────────────────────────────────────────────────────

def resume_writer(job_title: str, experience_bullets: str,
                  target_role: str, industry: str) -> Prompt:
    return Prompt(
        system=(
            "You are a professional resume writer with 15 years of experience "
            "placing candidates at Fortune 500 companies. You write ATS-optimised, "
            "achievement-focused resumes. Every bullet starts with a strong action verb "
            "and quantifies impact wherever possible."
        ),
        user=(
            f"Write a professional resume for a {job_title} targeting a {target_role} role "
            f"in the {industry} industry.\n\n"
            f"Experience context:\n{experience_bullets}\n\n"
            "Include:\n"
            "- Professional Summary (3 sentences, keyword-rich)\n"
            "- Work Experience section (STAR-formatted bullets)\n"
            "- Skills section (hard + soft, ATS-friendly)\n"
            "- Education placeholder\n\n"
            "Return in clean markdown. Optimise for ATS parsing."
        ),
    )


def cover_letter(company: str, role: str, candidate_summary: str) -> Prompt:
    return Prompt(
        system=(
            "You are a career coach who writes compelling, personalised cover letters "
            "that get callbacks. You avoid generic phrases and focus on specific value "
            "the candidate brings to the company."
        ),
        user=(
            f"Write a compelling cover letter for {candidate_summary} applying to "
            f"the {role} role at {company}.\n\n"
            "3 paragraphs: hook / proof of value / CTA. Under 300 words. "
            "Confident, specific, no clichés."
        ),
    )


# ── Email Marketing ───────────────────────────────────────────────────────────

def email_sequence(product: str, pain_point: str, steps: int = 5) -> Prompt:
    return Prompt(
        system=(
            "You are a direct-response email copywriter who has generated millions "
            "in revenue for info-product businesses. You understand the buyer journey, "
            "objection handling, and the perfect balance of value and pitch. "
            "You write like a trusted friend, not a marketer."
        ),
        user=(
            f"Write a {steps}-email nurture sequence selling '{product}'.\n"
            f"Core pain point: {pain_point}\n\n"
            "For each email provide:\n"
            "- Subject line (+ A/B variant)\n"
            "- Preview text (40 chars)\n"
            "- Full email body\n"
            "- Send timing (e.g. Day 0, Day 2…)\n\n"
            "Email 1: Welcome + value bomb (no pitch)\n"
            "Emails 2-4: Educate + social proof + objection handling\n"
            f"Email {steps}: Soft close with urgency\n\n"
            "Return as JSON array of email objects."
        ),
    )


def cold_email(prospect_role: str, product: str, value_prop: str) -> Prompt:
    return Prompt(
        system=(
            "You are a B2B cold email specialist with a 40%+ reply rate. "
            "You write ultra-short, personalised cold emails that don't sound automated. "
            "Under 75 words, one clear ask."
        ),
        user=(
            f"Write a cold email to a {prospect_role} about {product}.\n"
            f"Value proposition: {value_prop}\n\n"
            "Include subject line + body. No buzzwords. End with a soft CTA (question, not a link)."
        ),
    )


# ── Social Media ─────────────────────────────────────────────────────────────

def social_media_pack(brand: str, niche: str, platforms: list[str],
                       posts_per_platform: int = 5) -> Prompt:
    platforms_str = ", ".join(platforms)
    return Prompt(
        system=(
            "You are a social media strategist who has grown brand accounts to "
            "100k+ followers. You understand platform-specific formats, hooks, "
            "and the algorithms. You write scroll-stopping content."
        ),
        user=(
            f"Create a social media content pack for '{brand}' in the '{niche}' niche.\n"
            f"Platforms: {platforms_str}\n"
            f"Posts per platform: {posts_per_platform}\n\n"
            "For each post include:\n"
            "- Platform\n- Hook (first line)\n- Full caption\n"
            "- Hashtags (platform-appropriate)\n- Best posting time\n- Content type "
            "(carousel/reel/tweet/etc.)\n\n"
            "Return as JSON array."
        ),
    )


def linkedin_post(topic: str, personal_story: Optional[str] = None) -> Prompt:
    return Prompt(
        system=(
            "You write viral LinkedIn posts that feel authentic, spark conversation, "
            "and position the author as a thought leader. You use the proven hook-story-insight "
            "framework. No corporate speak."
        ),
        user=(
            f"Write a LinkedIn post about: {topic}\n"
            f"{('Personal story context: ' + personal_story) if personal_story else ''}\n\n"
            "Format: short punchy hook (1-2 lines) → story/insight (5-8 lines) → "
            "takeaway → question to drive comments. Use line breaks generously."
        ),
    )


# ── Product / E-commerce ──────────────────────────────────────────────────────

def product_description(product_name: str, features: str,
                         target_customer: str) -> Prompt:
    return Prompt(
        system=(
            "You are a conversion copywriter who writes product descriptions that sell. "
            "You lead with benefits, not features. You paint a picture of the customer's "
            "life after buying. You eliminate objections pre-emptively."
        ),
        user=(
            f"Write a product description for: {product_name}\n"
            f"Features: {features}\n"
            f"Target customer: {target_customer}\n\n"
            "Output:\n"
            "1. Hero headline (power + benefit)\n"
            "2. Subheadline (emotional hook)\n"
            "3. 3-sentence lead paragraph\n"
            "4. 5 bullet benefits (not features)\n"
            "5. Social proof placeholder\n"
            "6. CTA button text (2 variants)\n\n"
            "Return markdown."
        ),
    )


# ── Business Automation ───────────────────────────────────────────────────────

def business_plan_section(business_type: str, section: str,
                            market: str) -> Prompt:
    return Prompt(
        system=(
            "You are a startup advisor who has helped 200+ companies raise funding. "
            "You write crisp, data-backed business plan sections that investors actually read."
        ),
        user=(
            f"Write the '{section}' section of a business plan for a {business_type} "
            f"targeting the {market} market.\n\n"
            "Be specific, use industry benchmarks, include realistic projections. "
            "500-700 words. Return markdown."
        ),
    )


def niche_research(niche: str) -> Prompt:
    return Prompt(
        system=(
            "You are a market researcher who identifies profitable online niches. "
            "You think in revenue potential, competition gaps, and monetisation paths."
        ),
        user=(
            f"Do a deep niche analysis on: '{niche}'\n\n"
            "Cover:\n"
            "1. Market size & growth trend\n"
            "2. Top 5 pain points (buyer language)\n"
            "3. Monetisation methods ranked by revenue potential\n"
            "4. Competition level (1-10) with moat opportunities\n"
            "5. 3 quick-win content angles\n"
            "6. Recommended first product ($0 to build)\n\n"
            "Return as structured JSON."
        ),
    )

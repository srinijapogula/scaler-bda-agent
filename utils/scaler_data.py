"""
Verified Scaler program facts for LLM-grounded PDF content.
Keep this in sync with official collateral; do not invent policies here.
"""

from __future__ import annotations

import json

SCALER_DATA = {
    "academy": {
        "name": "Scaler Academy: Modern Software & AI Engineering",
        "duration": "12 months",
        "price": "~₹3.5L",
        "target": "0-7 YoE software engineers",
        "curriculum_highlights": [
            "DSA (Arrays, Recursion, DP, Graphs, Heaps)",
            "System Design",
            "Full Stack Development",
            "AI & Agents: Prompt Engineering, RAG, Multi-agent orchestration",
            "Backend Architecture",
            "Agentic AI Elective",
        ],
        "placement": {
            "hiring_partners": "900+",
            "alumni_network": "100,000+",
            "median_salary_hike": "~110% for DS/ML track (from their website)",
        },
        "differentiators": [
            "Live classes 3x/week with industry instructors",
            "1:1 mentorship with active industry professionals",
            "50+ hands-on projects and real-world case studies",
            "AI mock interviews with live avatars",
            "Curriculum updates included at no extra cost",
        ],
        "financing": "EMI options available",
        "entrance_test": "Required for admission - gates access to second call and enrollment",
    },
    "data_science": {
        "name": "Scaler Data Science & ML",
        "duration": "12+ months",
        "curriculum_highlights": [
            "SQL, Python, Statistics",
            "Machine Learning & MLOps",
            "Generative AI specialization",
            "End-to-end: raw data to deployed model",
        ],
    },
    "devops": {
        "name": "Scaler DevOps & Cloud",
        "duration": "9 months",
    },
}

# Honest, grounded reply framings for BDAs — do not add numbers or promises beyond SCALER_DATA.
COMMON_OBJECTIONS = {
    "Why pay 3.5L when free content exists?": (
        "Free resources are useful for self-starters, but Scaler is built around structure: live classes "
        "(3x/week with industry instructors), 1:1 mentorship with practicing professionals, 50+ hands-on projects, "
        "and career support tied to 900+ hiring partners and a large alumni community. The trade-off is guided "
        "pace, accountability, and depth versus piecing content alone. If you want a line-by-line comparison "
        "to your personal situation, we'd be happy to share specifics on your next call."
    ),
    "What salary jump can I expect?": (
        "Outcomes depend on your background, role, market, and effort — we don't quote personal salary "
        "guarantees. In our structured data we only cite a median salary hike figure for the DS/ML track "
        "as published on Scaler's website (~110%); that may not apply to other tracks or to your profile. "
        "For benchmarks that fit your experience and geography, we'd be happy to share specifics on your next call."
    ),
    "Is the curriculum actually updated/applied?": (
        "Scaler lists curriculum updates included at no extra cost and AI/ML-era topics (e.g., agents, RAG) "
        "in program highlights. How often modules change and what shipped in your cohort is something "
        "admissions can walk through precisely. We'd be happy to share specifics on your next call rather "
        "than guessing dates or release notes here."
    ),
    "What if I can't clear the entrance test?": (
        "Admission requires clearing the entrance test; it gates access to the second call and enrollment. "
        "Exact retake rules, prep resources, and timelines are set by admissions and can vary — we'd be "
        "happy to share specifics on your next call so you know exactly what applies to you."
    ),
    "How do people afford this?": (
        "We document that EMI options exist alongside the roughly ~₹3.5L price point for Academy in this sheet. "
        "Scholarship eligibility, payment plans, and what's available for your cohort are confirmed only through "
        "official admissions. We'd be happy to share specifics on your next call."
    ),
    "Will the cohort be at my level?": (
        "Academy is positioned for 0–7 YoE software engineers; Data Science & ML and DevOps tracks have their "
        "own structures. How peer grouping, pacing, and prerequisites work for your exact batch is best confirmed "
        "by admissions. We'd be happy to share specifics on your next call."
    ),
    "Are instructors practitioners or academics?": (
        "What we verify here is that live classes are with industry instructors and 1:1 mentorship is with "
        "active industry professionals — plus project and interview-practice elements as listed in program "
        "differentiators. Exact faculty rosters and guest experts change by cohort; we'd be happy to share "
        "specifics on your next call."
    ),
}

PERSONA_TEMPLATE_HINTS = {
    "career_switcher": "Tone: confident, transition-focused, ROI on time invested, mid-career empathy.",
    "senior_professional": "Tone: concise, strategic, leadership and depth; respect seniority.",
    "newcomer_student": "Tone: supportive, clear definitions, low jargon; encourage without patronizing.",
}


def get_facts_block() -> str:
    """Return canonical structured data + objection framings for injection into prompts (JSON for clarity)."""
    instructions = (
        "Use ONLY the facts and objection framings below. "
        "Do not invent fees, cohort dates, pass rates, salaries, or policies. "
        "If the lead asks for detail not present here, say you'd be happy to share specifics "
        "on the next call with admissions rather than fabricating."
    )
    payload = {
        "instructions": instructions,
        "SCALER_DATA": SCALER_DATA,
        "COMMON_OBJECTIONS": COMMON_OBJECTIONS,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def template_for_persona(persona_key: str) -> str:
    """Map UI persona selection to template filename (without path)."""
    mapping = {
        "Career switcher": "career_switcher.html",
        "Senior professional": "senior_professional.html",
        "Newcomer / student": "newcomer_student.html",
    }
    return mapping.get(persona_key, "career_switcher.html")


def template_for_persona_slug(slug: str) -> str:
    """Map analyzer slug to template filename."""
    s = (slug or "career_switcher").strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "career_switcher": "career_switcher.html",
        "senior_professional": "senior_professional.html",
        "newcomer_student": "newcomer_student.html",
    }
    return mapping.get(s, "career_switcher.html")


def persona_ui_label_to_slug(label: str) -> str:
    """Map Streamlit selectbox label (non-auto) to slug."""
    mapping = {
        "Career switcher": "career_switcher",
        "Senior professional": "senior_professional",
        "Newcomer / student": "newcomer_student",
    }
    return mapping.get(label, "career_switcher")

"""Generate personalized PDF copy + WhatsApp covering message via Claude."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from anthropic import APIConnectionError, APIError, Anthropic
from anthropic import NotFoundError as AnthropicNotFoundError
from anthropic import RateLimitError as AnthropicRateLimitError

from utils.scaler_data import get_facts_block

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"

ALLOWED_PERSONAS = frozenset({"career_switcher", "senior_professional", "newcomer_student"})


def _client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set.")
    return Anthropic(api_key=api_key)


def _strip_code_fences(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned


def _sanitize_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)
    html = re.sub(r"\son\w+\s*=\s*([\"']).*?\1", "", html, flags=re.IGNORECASE)
    return _normalize_for_pdf(html)


def _normalize_for_pdf(text: str) -> str:
    """Avoid glyphs that often break in PDF (rupee, odd unicode)."""
    if not text:
        return text
    text = text.replace("\u20b9", "Rs. ")
    text = text.replace("₹", "Rs. ")
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    return text


def generate_pdf_content(
    *,
    lead_profile: dict[str, Any],
    transcript_extract: dict[str, Any],
    bda_name: str,
    lead_name: str,
    scaler_data: str | None = None,
    template_persona_slug: str = "career_switcher",
) -> dict[str, Any]:
    """
    Generate personalized PDF sections and WhatsApp covering text using Claude.

    Args:
        lead_profile: CRM-style fields (Name, role, track, notes, etc.).
        transcript_extract: Output of ``extract_transcript_insights`` (open_questions,
            emotional_drivers, trust_blockers, persona_type, key_quotes).
        scaler_data: Serialized verified program JSON for prompts; defaults to ``get_facts_block()``.
        template_persona_slug: Persona slug for tone (career_switcher / senior_professional / newcomer_student).

    Returns:
        {
          "sections": [{"heading": str, "body_html": str}, ...],
          "greeting": str,
          "cta_text": str,
          "covering_message": str,
          "persona_type": str,
        }
    """
    facts = (scaler_data or "").strip() or get_facts_block()

    slug = (template_persona_slug or transcript_extract.get("persona_type") or "career_switcher").strip().lower()
    slug = slug.replace("-", "_").replace(" ", "_")
    if slug not in ALLOWED_PERSONAS:
        slug = str(transcript_extract.get("persona_type") or "career_switcher").strip().lower()
        if slug not in ALLOWED_PERSONAS:
            slug = "career_switcher"

    safe_lead = (lead_name or "").strip() or "there"
    safe_bda = (bda_name or "your BDA").strip()

    extract_json = json.dumps(transcript_extract, ensure_ascii=False, indent=2)
    profile_json = json.dumps(lead_profile or {}, ensure_ascii=False, indent=2)

    open_qs = transcript_extract.get("open_questions") or []
    if not isinstance(open_qs, list):
        open_qs = []
    open_qs = [str(x).strip() for x in open_qs if str(x).strip()][:8]
    if not open_qs:
        open_qs = ["General program fit and next steps"]

    system_lead = (
        f"You are writing a short, personalized follow-up for {safe_lead} after their Scaler sales call. "
        "This goes as a WhatsApp PDF -- they will read it on their phone. "
        "It must build enough trust for them to take the entrance test.\n"
    )
    system_rules = """
ABSOLUTE RULES:

TOTAL content must fit 2-3 A4 pages. If in doubt, be shorter.
Each answer: 3-5 sentences. No essays. No filler.
Write like a smart friend who works at Scaler, not a salesperson.
Use their exact words from the call when referencing their concerns.
ONLY use verified data from the SCALER_DATA provided. Never invent facts.
For anything not in verified data: "Happy to share specifics on your next call."
Always write Indian Rupee as "Rs." or "INR" -- never use the rupee glyph (U+20B9) as it may not render in PDF.
Use "Rs. 3.5L" not a rupee symbol before amounts.
No unicode symbols. Use plain ASCII punctuation only in output strings.
Every sentence must be specific to THIS person. Generic = failure.
DO NOT repeat the same point twice.
DO NOT use corporate jargon like "leverage", "synergy", "holistic".

TONE GUIDE BY PERSONA:

career_switcher: Direct, action-oriented. Here is why the math works for you.
senior_professional: Peer-level, no-BS. Data over promises. Respect their intelligence.
newcomer_student: Warm, encouraging, addresses fears honestly. Big-sister energy.

OUTPUT (JSON only, no markdown):
{
"greeting": "2 sentences. Reference something SPECIFIC from their call. Warm but brief.",
"sections": [
{
"heading": "Mirror their actual question in plain language",
"body_html": "<p>3-5 sentences. Direct answer first, then 1-2 evidence points from verified data. Use <strong> sparingly for key facts only.</p>"
}
],
"cta_text": "1 sentence about the entrance test. Encouraging, not pushy.",
"covering_message": "2 lines max WhatsApp message. Casual. Reference one thing from their call."
}
MAX 4 sections. Short headings. Short answers. This is a WhatsApp PDF, not a whitepaper.
""".strip()

    system = system_lead + "\n" + system_rules

    user = (
        f"TEMPLATE_PERSONA_SLUG (use this tone): {slug}\n\n"
        f"VERIFIED_SCALER_JSON (SCALER_DATA only this for facts):\n{facts}\n\n"
        f"BDA name: {safe_bda}\n"
        f"Lead name: {safe_lead}\n\n"
        "Lead profile:\n"
        f"{profile_json}\n\n"
        "Transcript analysis (structured):\n"
        f"{extract_json}\n\n"
        "Answer these open_questions across sections (max 4 sections; merge overlaps):\n"
        f"{json.dumps(open_qs, ensure_ascii=False)}\n"
    )

    try:
        client = _client()
        message = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            temperature=0.35,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except AnthropicNotFoundError as e:
        raise RuntimeError(
            f"Anthropic model not found: `{MODEL}`. "
            "Set `ANTHROPIC_MODEL` in `.env` to a model available for your API key."
        ) from e
    except (APIConnectionError, AnthropicRateLimitError, APIError) as e:
        raise RuntimeError(f"Anthropic API error while generating PDF content: {e}") from e

    raw = message.content[0].text.strip() if message.content else ""
    if not raw:
        raise RuntimeError("Empty PDF content from model.")

    try:
        payload = json.loads(_strip_code_fences(raw))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON for PDF payload: {e}. Snippet: {raw[:500]}") from e

    for key in ("sections", "greeting", "cta_text", "covering_message"):
        if key not in payload:
            raise RuntimeError(f"PDF payload missing key: {key}")

    sections = payload["sections"]
    if not isinstance(sections, list) or not sections:
        raise RuntimeError("PDF payload sections must be a non-empty list.")

    cleaned_sections: list[dict[str, str]] = []
    for item in sections:
        if not isinstance(item, dict):
            continue
        h = _normalize_for_pdf(str(item.get("heading", "")).strip())
        b = _sanitize_html(str(item.get("body_html", "")).strip())
        if h and b:
            cleaned_sections.append({"heading": h, "body_html": b})

    cleaned_sections = cleaned_sections[:4]

    if not cleaned_sections:
        raise RuntimeError("No valid sections after sanitization.")

    out_persona = str(payload.get("persona_type", slug)).strip().lower().replace("-", "_")
    if out_persona not in ALLOWED_PERSONAS:
        out_persona = slug

    greeting = _normalize_for_pdf(str(payload.get("greeting", "")).strip())
    if not greeting:
        greeting = (
            f"Hi {safe_lead}, thanks for the conversation. This note ties directly to what you asked "
            f"and what matters next for you."
        )

    cta_text = _normalize_for_pdf(str(payload.get("cta_text", "")).strip())
    if not cta_text:
        cta_text = "Reply here or tell me when you’re free to continue with admissions."

    covering = _normalize_for_pdf(str(payload.get("covering_message", "")).strip())
    if not covering:
        covering = (
            f"Hi {safe_lead}, sending the brief we discussed—covers your open questions. "
            f"Ping me when you’re ready for the next step."
        )

    return {
        "sections": cleaned_sections,
        "greeting": greeting,
        "cta_text": cta_text,
        "covering_message": covering,
        "persona_type": out_persona,
    }


def generate_pdf_payload(
    *,
    lead_name: str,
    bda_name: str,
    lead_profile: dict[str, Any],
    questions: list[str],
    template_persona: str,
) -> dict[str, Any]:
    """
    Back-compat when only a question list exists (no full transcript analysis).
    Prefer :func:`extract_transcript_insights` + :func:`generate_pdf_content`.
    """
    slug_map = {
        "Career switcher": "career_switcher",
        "Senior professional": "senior_professional",
        "Newcomer / student": "newcomer_student",
    }
    slug = slug_map.get(template_persona, "career_switcher")
    extracted: dict[str, Any] = {
        "open_questions": questions or ["General program fit and next steps"],
        "emotional_drivers": "Legacy path: full transcript not analyzed—lean on CRM profile and listed questions.",
        "trust_blockers": "Legacy path: infer cautiously or use “We’ll share more details on your next call.”",
        "persona_type": slug,
        "key_quotes": [],
    }
    out = generate_pdf_content(
        lead_profile=lead_profile,
        transcript_extract=extracted,
        bda_name=bda_name,
        lead_name=lead_name,
        scaler_data=None,
        template_persona_slug=slug,
    )
    out["title"] = f"{(lead_name or '').strip() or 'Lead'} — Scaler follow-up"
    out["subtitle"] = ""
    return out


def generate_whatsapp_cover_message(
    *,
    lead_name: str,
    bda_name: str,
    pdf_title: str,
    questions: list[str],
) -> str:
    """
    Legacy one-off cover generator. Prefer ``generate_pdf_content`` ``covering_message``.
    """
    synthetic = "Follow-up themes:\n" + "\n".join(f"- {q}" for q in (questions or [])[:12])
    extracted = {
        "open_questions": questions or ["General follow-up"],
        "emotional_drivers": "",
        "trust_blockers": "",
        "persona_type": "career_switcher",
        "key_quotes": [],
    }
    payload = generate_pdf_content(
        lead_profile={"Name": lead_name, "Notes": synthetic},
        transcript_extract=extracted,
        bda_name=bda_name,
        lead_name=lead_name,
        scaler_data=get_facts_block(),
        template_persona_slug="career_switcher",
    )
    return payload["covering_message"]

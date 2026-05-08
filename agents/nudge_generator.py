"""Generate pre-sales WhatsApp nudges for BDAs using Claude."""

from __future__ import annotations

import os
from typing import Any

from anthropic import APIConnectionError, APIError, Anthropic
from anthropic import NotFoundError as AnthropicNotFoundError
from anthropic import RateLimitError as AnthropicRateLimitError

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"

_MAX_WORDS = 200


def _client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set.")
    return Anthropic(api_key=api_key)


def _first_non_empty(profile: dict[str, Any], *keys: str) -> str:
    for k in keys:
        if k not in profile:
            continue
        v = profile[k]
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _compose_lead_fields(
    lead_profile: dict[str, Any],
    *,
    name: str | None = None,
    profile: str | None = None,
    intent: str | None = None,
    linkedin_background: str | None = None,
) -> tuple[str, str, str, str]:
    """
    Resolve name, profile, intent, and LinkedIn/background from explicit args or CRM-style dict keys.
    """
    n = (name or "").strip() or _first_non_empty(
        lead_profile, "Name", "name", "Lead name"
    )

    p = (profile or "").strip()
    if not p:
        chunks: list[str] = []
        role = _first_non_empty(
            lead_profile,
            "Current role",
            "Profile",
            "profile",
        )
        if role:
            chunks.append(role)
        exp = _first_non_empty(
            lead_profile,
            "Experience (years)",
            "Experience",
            "YoE",
        )
        if exp:
            chunks.append(f"~{exp} YoE")
        contact_bits = []
        for key in ("Phone", "phone", "Email", "email"):
            bit = _first_non_empty(lead_profile, key)
            if bit and bit not in contact_bits:
                contact_bits.append(bit)
        if contact_bits:
            chunks.append(" · ".join(contact_bits))
        p = " · ".join(chunks) if chunks else ""

    i = (intent or "").strip()
    if not i:
        i = _first_non_empty(
            lead_profile,
            "Intent",
            "intent",
            "Target track",
            "Goals",
        )

    lb = (linkedin_background or "").strip()
    if not lb:
        lb = _first_non_empty(
            lead_profile,
            "LinkedIn",
            "linkedin",
            "Linkedin URL",
            "Link",
            "URL",
        )
        notes = _first_non_empty(lead_profile, "Notes", "notes", "Lead context")
        if notes:
            if lb:
                lb = f"{lb} — {notes}"
            else:
                lb = notes

    return (
        n or "Unknown",
        p or "(none provided)",
        i or "(none provided)",
        lb or "(none provided)",
    )


SYSTEM_PROMPT = """You are prepping a Business Development Associate at Scaler Academy for an upcoming call.

Write a single WhatsApp-style nudge they can skim on a phone in under two minutes. Sound like a teammate texting: short lines, plain text, no corporate jargon or stiff memo voice.

Hard rules:
- Strictly under {max_words} words (count before you finish).
- Specific to THIS lead; ban generic template filler (“excited to connect”, etc. unless tied to their input).
- Every substantive line or bullet must start with FACT: or INFERRED: or UNKNOWN: 
  (FACT = explicitly given in LEAD INPUT; INFERRED = tight guess—add “(from …)” in a few words; UNKNOWN = you must discover—say what to ask).
- Use these section headings exactly, in order (keep each section compact):
  Quick Profile
  Why They’re Interested
  Opening Hook
  Angles That’ll Resonate
  Objections to Expect
  What We Don’t Know
- No markdown code blocks, no ``` fences. Line breaks and light “•” bullets OK.
- Do not invent employers, compensation, offers, or admissions rules. Missing info → UNKNOWN or omit.
- Do not promise outcomes or quote fees unless they appear as FACT in the input.

Output only the message body.""".format(max_words=_MAX_WORDS)


def generate_pre_sales_nudge(
    *,
    bda_name: str,
    lead_profile: dict[str, Any],
    name: str | None = None,
    profile: str | None = None,
    intent: str | None = None,
    linkedin_background: str | None = None,
) -> str:
    """
    Produce a pre-call WhatsApp briefing for the BDA using Claude.

    Lead fields can be passed explicitly or read from ``lead_profile`` (e.g. Name, Current role,
    Target track, Notes, LinkedIn).

    Returns the nudge as plain text.

    Raises:
        ValueError: if ANTHROPIC_API_KEY is missing
        RuntimeError: on empty model output or API errors
    """
    client = _client()
    safe_bda = (bda_name or "there").strip() or "there"

    lead_name, prof, intent_s, bg = _compose_lead_fields(
        lead_profile,
        name=name,
        profile=profile,
        intent=intent,
        linkedin_background=linkedin_background,
    )

    user = f"""BDA first name (for tone only): {safe_bda}

LEAD INPUT (use only this + common sense; mark FACT/INFERRED/UNKNOWN as required):
- Name: {lead_name}
- Profile / current situation: {prof}
- Intent / what they want from the conversation: {intent_s}
- LinkedIn or other background: {bg}

Write the WhatsApp nudge now."""

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=1200,
            temperature=0.35,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
        )
    except AnthropicNotFoundError as e:
        raise RuntimeError(
            f"Anthropic model not found: `{MODEL}`. "
            "Set `ANTHROPIC_MODEL` in `.env` to a model available for your API key."
        ) from e
    except (APIConnectionError, AnthropicRateLimitError, APIError) as e:
        raise RuntimeError(f"Anthropic API error while generating nudge: {e}") from e

    text = message.content[0].text.strip() if message.content else ""
    if not text:
        raise RuntimeError("Model returned an empty nudge.")

    return text

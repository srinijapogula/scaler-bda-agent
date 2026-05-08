"""Extract structured insights from BDA call transcripts via Claude."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from anthropic import APIConnectionError, APIError, Anthropic
from anthropic import NotFoundError as AnthropicNotFoundError
from anthropic import RateLimitError as AnthropicRateLimitError

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"

ALLOWED_PERSONAS = frozenset({"career_switcher", "senior_professional", "newcomer_student"})

_SYSTEM = """You analyze transcripts of sales/admissions calls for Scaler Academy (BDAs and leads).

Return a single JSON object only (no markdown, no code fences) with exactly these keys:
{
  "open_questions": string[],
  "emotional_drivers": string,
  "trust_blockers": string,
  "persona_type": "career_switcher" | "senior_professional" | "newcomer_student",
  "key_quotes": string[]
}

Rules:
- open_questions: unresolved questions, worries, or information gaps the lead still has (lead's voice when possible). Deduplicate. Empty array only if truly none.
- emotional_drivers: 2-4 sentences on what motivates them (stability, growth, prestige, fear of falling behind, family expectations, etc.) grounded in the transcript.
- trust_blockers: 2-4 sentences on skepticism, risk concerns, past bad experiences, or what would make them hesitate—grounded in the transcript.
- persona_type: pick ONE slug:
  - career_switcher: moving toward product / stronger tech company, Services → product, 2-7 YoE, urgency to level up.
  - senior_professional: high seniority or top-tier employer, skeptical, wants depth and proof, minimal fluff.
  - newcomer_student: student or 0-1 YoE, budget/capacity concerns, needs reassurance and clarity on basics.
  If ambiguous, choose the closest match from wording and context.
- key_quotes: up to 8 short verbatim (or near-verbatim) quotes from the LEAD that capture tone/concerns. No long paragraphs.

Do not invent dialogue not supported by the transcript."""


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


def _as_text(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        parts = [str(x).strip() for x in val if str(x).strip()]
        return "; ".join(parts)
    return str(val).strip()


def _normalize_insights(data: dict[str, Any], *, max_open_questions: int) -> dict[str, Any]:
    oq = data.get("open_questions", [])
    if not isinstance(oq, list):
        oq = []
    questions: list[str] = []
    seen: set[str] = set()
    for item in oq:
        if isinstance(item, str) and item.strip():
            k = item.strip().lower()
            if k in seen:
                continue
            seen.add(k)
            questions.append(item.strip())
    questions = questions[:max_open_questions]

    persona = str(data.get("persona_type", "")).strip().lower().replace("-", "_").replace(" ", "_")
    if persona not in ALLOWED_PERSONAS:
        persona = "career_switcher"

    kq = data.get("key_quotes", [])
    if not isinstance(kq, list):
        kq = []
    quotes: list[str] = []
    for item in kq:
        if isinstance(item, str) and item.strip():
            q = item.strip()
            if len(q) > 400:
                q = q[:397] + "…"
            quotes.append(q)
    quotes = quotes[:8]

    return {
        "open_questions": questions,
        "emotional_drivers": _as_text(data.get("emotional_drivers")) or "(not stated clearly)",
        "trust_blockers": _as_text(data.get("trust_blockers")) or "(not stated clearly)",
        "persona_type": persona,
        "key_quotes": quotes,
    }


def extract_transcript_insights(
    *,
    transcript: str,
    lead_profile: dict[str, Any] | None = None,
    max_open_questions: int = 16,
) -> dict[str, Any]:
    """
    Call Claude to extract open questions, emotional drivers, trust posture, persona, and key quotes.

    Returns:
        {
          "open_questions": list[str],
          "emotional_drivers": str,
          "trust_blockers": str,
          "persona_type": str  # career_switcher | senior_professional | newcomer_student
          "key_quotes": list[str],
        }
    """
    text = (transcript or "").strip()
    if not text:
        raise ValueError("Transcript is empty.")

    profile = lead_profile or {}
    profile_lines: list[str] = []
    for k, v in profile.items():
        if v is None or str(v).strip() == "":
            continue
        profile_lines.append(f"- {k}: {v}")
    profile_block = "\n".join(profile_lines) if profile_lines else "(no CRM profile provided)"

    user = (
        "Lead profile (CRM):\n"
        f"{profile_block}\n\n"
        "Call transcript:\n"
        f"{text}\n"
    )

    try:
        client = _client()
        message = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            temperature=0.2,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
    except AnthropicNotFoundError as e:
        raise RuntimeError(
            f"Anthropic model not found: `{MODEL}`. "
            "Set `ANTHROPIC_MODEL` in `.env` to a model available for your API key."
        ) from e
    except (APIConnectionError, AnthropicRateLimitError, APIError) as e:
        raise RuntimeError(f"Anthropic API error while extracting transcript insights: {e}") from e

    raw = message.content[0].text.strip() if message.content else ""
    if not raw:
        raise RuntimeError("Model returned empty transcript analysis.")

    try:
        data = json.loads(_strip_code_fences(raw))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from transcript extractor: {e}. Raw: {raw[:600]}") from e

    if not isinstance(data, dict):
        raise RuntimeError("Transcript extractor output must be a JSON object.")

    return _normalize_insights(data, max_open_questions=max_open_questions)


def extract_open_questions(
    *,
    transcript: str,
    lead_profile: dict[str, Any],
    max_questions: int = 12,
) -> list[str]:
    """
    Back-compat helper: returns only ``open_questions`` (deduped, capped).
    """
    data = extract_transcript_insights(
        transcript=transcript,
        lead_profile=lead_profile,
        max_open_questions=max_questions,
    )
    return data["open_questions"]

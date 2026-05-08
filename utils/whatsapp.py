"""Send WhatsApp messages via Twilio (sandbox or production sender)."""

from __future__ import annotations

import os
import re

from dotenv import load_dotenv
import requests
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client


def _clean_env(value: str) -> str:
    v = (value or "").strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1].strip()
    return v.strip().strip("`").replace("\u200b", "")


def _looks_like_placeholder(value: str) -> bool:
    v = _clean_env(value).lower()
    return v in {"", "your_twilio_account_sid", "your_twilio_auth_token", "changeme", "xxx"}


def _validate_twilio_creds(sid: str, token: str) -> None:
    if _looks_like_placeholder(sid) or _looks_like_placeholder(token):
        raise ValueError("Twilio credentials look like placeholders. Set real TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.")
    if not sid.startswith("AC") or len(sid) < 20:
        raise ValueError("TWILIO_ACCOUNT_SID format looks invalid (expected AC...).")
    if len(token) < 16:
        raise ValueError("TWILIO_AUTH_TOKEN format looks invalid.")


def _get_client() -> Client:
    # Ensure latest .env values are loaded even if edited while Streamlit is running.
    load_dotenv(override=True)
    sid = _clean_env(os.environ.get("TWILIO_ACCOUNT_SID", ""))
    token = _clean_env(os.environ.get("TWILIO_AUTH_TOKEN", ""))
    if not sid or not token:
        raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set.")
    _validate_twilio_creds(sid, token)
    return Client(sid, token)


def _get_whatsapp_from() -> str:
    from_id = _clean_env(os.environ.get("TWILIO_WHATSAPP_FROM", ""))
    if not from_id:
        raise ValueError("TWILIO_WHATSAPP_FROM is not set (e.g. whatsapp:+14155238886).")
    normalized = format_whatsapp_number(from_id)
    if normalized != "whatsapp:+14155238886" and "sandbox" in from_id.lower():
        raise ValueError("TWILIO_WHATSAPP_FROM looks incorrect. For sandbox use whatsapp:+14155238886.")
    return normalized


def _raise_twilio_error(e: TwilioRestException) -> None:
    code = getattr(e, "code", None)
    if code == 20003:
        raise RuntimeError(
            "Twilio authentication failed (20003). Check TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN in `.env`, "
            "remove extra spaces/quotes, and ensure SID and token are from the same Twilio project/account."
        ) from e
    raise RuntimeError(f"Twilio failed to send message: {e.msg} (code {e.code})") from e


def test_twilio_auth() -> str:
    """
    Validate Twilio credentials by fetching the current account resource.

    Returns the account SID on success.
    """
    client = _get_client()
    try:
        account = client.api.accounts(client.username).fetch()
    except TwilioRestException as e:
        _raise_twilio_error(e)
    return str(account.sid)


def format_whatsapp_number(raw: str) -> str:
    """
    Normalize to ``whatsapp:+E164digits`` (no spaces). Accepts optional ``whatsapp:`` prefix.
    """
    s = (raw or "").strip().replace(" ", "")
    if not s:
        raise ValueError("Phone number is empty.")

    lower = s.lower()
    if lower.startswith("whatsapp:"):
        rest = s.split(":", 1)[1].strip()
    else:
        rest = s

    if rest.startswith("+"):
        digits = "".join(c for c in rest[1:] if c.isdigit())
        core = "+" + digits
    else:
        digits = "".join(c for c in rest if c.isdigit())
        core = "+" + digits

    if len(core) < 9:
        raise ValueError(f"Invalid phone number (too short after normalization): {raw!r}")
    return f"whatsapp:{core}"


def send_text_message(to_number: str, message: str) -> str:
    """
    Send a WhatsApp text via Twilio.

    Returns the Message SID on success.
    """
    from_id = _get_whatsapp_from()
    to_id = format_whatsapp_number(to_number)
    body = (message or "").strip()
    if not body:
        raise ValueError("Message body is empty.")

    client = _get_client()
    try:
        msg = client.messages.create(from_=from_id, to=to_id, body=body)
    except TwilioRestException as e:
        _raise_twilio_error(e)
    return str(msg.sid)


def send_pdf_message(to_number: str, message: str, pdf_url: str) -> str:
    """
    Send WhatsApp text with a PDF attachment (public HTTPS URL required by Twilio).

    Returns the Message SID on success.
    """
    from_id = _get_whatsapp_from()
    to_id = format_whatsapp_number(to_number)
    body = (message or "").strip()
    if not body:
        raise ValueError("Message body is empty.")

    url = (pdf_url or "").strip()
    if not url:
        raise ValueError("pdf_url is empty.")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise ValueError("pdf_url must be an http(s) URL reachable by Twilio for media.")

    client = _get_client()
    try:
        msg = client.messages.create(
            from_=from_id,
            to=to_id,
            body=body,
            media_url=[url],
        )
    except TwilioRestException as e:
        _raise_twilio_error(e)
    return str(msg.sid)


def send_whatsapp_text(*, to_number: str, body: str) -> str:
    """Backward-compatible alias for :func:`send_text_message`."""
    return send_text_message(to_number, body)


def upload_pdf_to_public_url(pdf_path: str) -> str:
    """Upload a local PDF to file.io and return a public URL."""
    path = (pdf_path or "").strip()
    if not path:
        raise ValueError("pdf_path is empty.")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"PDF file not found: {path}")

    with open(path, "rb") as f:
        response = requests.post(
            "https://file.io",
            files={"file": (os.path.basename(path), f, "application/pdf")},
            data={"expires": "1d"},
            timeout=30,
        )
    if response.status_code == 200:
        data = response.json()
        if data.get("success") and data.get("link"):
            return str(data["link"]).strip()
    raise RuntimeError("Failed to upload PDF to public URL")


def send_whatsapp_with_optional_pdf(
    *,
    to_number: str,
    body: str,
    pdf_url: str | None = None,
    pdf_path: str | None = None,
    pdf_bytes: bytes | None = None,
) -> dict:
    """
    Send WhatsApp; attach PDF if ``pdf_url`` is set or if legacy ``pdf_bytes`` + env allows a URL.

    For ``pdf_bytes`` without ``pdf_url``, upload to ``TWILIO_PUBLIC_MEDIA_PATH`` when
    ``TWILIO_PUBLIC_MEDIA_URL`` is configured (legacy).

    Returns dict: sid, had_attachment, attachment_url (optional), note (optional).
    """
    import uuid
    from pathlib import Path

    body = (body or "").strip()
    if not body:
        raise ValueError("Message body is empty.")

    media_url = None
    note: str | None = None

    # Prefer file.io upload so Twilio always gets a public HTTPS URL.
    if pdf_path:
        try:
            media_url = upload_pdf_to_public_url(pdf_path)
        except Exception:
            media_url = None

    if not media_url:
        media_url = (pdf_url or "").strip() or None

    if not media_url and pdf_bytes:
        media_dir = os.environ.get("TWILIO_PUBLIC_MEDIA_PATH", "public_media").strip() or "public_media"
        base_url = os.environ.get("TWILIO_PUBLIC_MEDIA_URL", "").strip()
        path = Path(media_dir)
        path.mkdir(parents=True, exist_ok=True)
        fname = f"scaler-brief-{uuid.uuid4().hex}.pdf"
        fpath = path / fname
        fpath.write_bytes(pdf_bytes)
        if base_url:
            media_url = base_url.rstrip("/") + "/" + fname
        else:
            note = "NO_PUBLIC_PDF_URL"

    if media_url:
        sid = send_pdf_message(to_number, body, media_url)
        return {
            "sid": sid,
            "had_attachment": True,
            "attachment_url": media_url,
            "note": note,
        }

    sid = send_text_message(to_number, body)
    return {
        "sid": sid,
        "had_attachment": False,
        "attachment_url": None,
        "note": note,
    }

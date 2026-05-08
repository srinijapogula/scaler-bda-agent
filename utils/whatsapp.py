"""Send WhatsApp messages via Twilio."""

from __future__ import annotations

import os
from dotenv import load_dotenv
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
    return format_whatsapp_number(from_id)


def _raise_twilio_error(e: TwilioRestException) -> None:
    code = getattr(e, "code", None)
    if code == 20003:
        raise RuntimeError(
            "Twilio authentication failed (20003). Check TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN in `.env`, "
            "remove extra spaces/quotes, and ensure SID and token are from the same Twilio project/account."
        ) from e
    raise RuntimeError(f"Twilio failed to send message: {e.msg} (code {e.code})") from e


def test_twilio_auth() -> str:
    client = _get_client()
    try:
        account = client.api.accounts(client.username).fetch()
    except TwilioRestException as e:
        _raise_twilio_error(e)
    return str(account.sid)


def format_whatsapp_number(raw: str) -> str:
    s = (raw or "").strip().replace(" ", "")
    if not s:
        raise ValueError("Phone number is empty.")
    if s.lower().startswith("whatsapp:"):
        s = s.split(":", 1)[1].strip()
    if not s.startswith("+"):
        s = "+" + "".join(c for c in s if c.isdigit())
    else:
        s = "+" + "".join(c for c in s[1:] if c.isdigit())
    if len(s) < 9:
        raise ValueError(f"Invalid phone number (too short after normalization): {raw!r}")
    return f"whatsapp:{s}"


def send_text_message(to_number: str, message: str) -> str:
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


def send_pdf_message(to_number: str, message: str, pdf_path: str) -> str:
    path = (pdf_path or "").strip()
    if not path:
        raise ValueError("pdf_path is empty.")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"PDF file not found: {path}")

    # Manual-share flow: send text only, BDA shares the downloaded PDF manually.
    manual_share_message = (
        "Hi there, thanks for your time on the call today! I've put together answers to the questions you raised.\n\n"
        "📄 Your personalized PDF is ready - your Scaler advisor will share it with you shortly.\n\n"
        "Let me know if you'd like to chat more!"
    )
    return send_text_message(to_number, manual_share_message)

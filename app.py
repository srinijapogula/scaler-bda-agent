"""Scaler BDA AI Assistant — Streamlit entrypoint."""

from __future__ import annotations

import html as html_lib
import io
import json
import os
import traceback
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from agents.audio_transcriber import transcribe_audio
from agents.nudge_generator import generate_pre_sales_nudge
from agents.pdf_content_generator import generate_pdf_content
from agents.transcript_extractor import extract_transcript_insights
from utils.pdf_renderer import render_pdf, static_pdf_url
from utils.scaler_data import get_facts_block, persona_ui_label_to_slug, template_for_persona_slug
from utils.whatsapp import send_pdf_message, send_text_message, send_whatsapp_with_optional_pdf, test_twilio_auth

load_dotenv(override=True)

APP_VERSION = "v2.1.0"

# Shown when WhatsApp text sends but Twilio cannot attach PDF (needs public HTTPS media URL).
PDF_ATTACHMENT_SETUP = """
**PDF was not attached to WhatsApp.** Twilio only downloads media from a **public HTTPS** URL (it cannot read your laptop or a private network).

**Do this (choose one):**

1. **Recommended:** Expose the project `static/` folder over HTTPS and set in `.env`:
   `STATIC_PUBLIC_BASE_URL=https://YOUR_HOST/static`  
   The app already saves each PDF under `static/` with the same filename as in the temp path. That full URL must return the PDF when opened in a browser.

2. **Alternative:** Set `TWILIO_PUBLIC_MEDIA_PATH` (writable folder) and `TWILIO_PUBLIC_MEDIA_URL` (HTTPS base URL for that folder).

3. **Local dev:** Run a tunnel (e.g. ngrok) to an HTTP server that serves `static/`, then set `STATIC_PUBLIC_BASE_URL` to that HTTPS base + `/static`.

Restart Streamlit after editing `.env`, regenerate the PDF, then **Approve & Send** again.
""".strip()
REQUIRED_ENV = (
    ("ANTHROPIC_API_KEY", "Claude (nudges, transcript, PDF)"),
    ("TWILIO_ACCOUNT_SID", "Twilio WhatsApp"),
    ("TWILIO_AUTH_TOKEN", "Twilio WhatsApp"),
    ("TWILIO_WHATSAPP_FROM", "Twilio WhatsApp sender"),
)

PRESETS = {
    "rohan": {
        "name": "Rohan Sharma",
        "profile": (
            "Software Engineer, TCS. 4 YoE. B.Tech CSE VIT Vellore 2020. "
            "SDE-2 at TCS for 4 years (banking clients: HDFC, Citi). Recent AWS Solutions Architect cert."
        ),
        "intent": "Want to switch to a product company, tired of service work, interested in AI engineering roles",
        "linkedin": (
            "B.Tech CSE VIT Vellore '20, SDE-2 at TCS 4 years (banking clients: HDFC, Citi), "
            "AWS Solutions Architect cert"
        ),
        "lead_whatsapp": "+919876543211",
        "transcript": (
            "BDA: Rohan, what's bringing you to Scaler? "
            "Rohan: I've been at TCS for 4 years. Banking projects. I want to move to a product company "
            "— and I keep seeing AI engineering roles and wondering if I'm already too late. "
            "BDA: Not too late. Have you looked at our AI Engineering program? "
            "Rohan: I've looked. Here's my question though — why should I pay Rs.3.5L when Andrew Ng has "
            "basically the same stuff for free on Coursera? What's actually different? "
            "BDA: Good question, let me get back to you on the specifics. "
            "Rohan: Also — realistically, what salary jump does someone like me get? If I'm going from "
            "14 LPA at TCS to 16 at another service company, the math doesn't work. "
            "BDA: We have data on that, I'll share. "
            "Rohan: One more — I want to build real LLM applications. RAG, agents, evals. "
            "Is your program on that, or is it more theoretical ML? "
            "BDA: We'll cover everything you need."
        ),
    },
    "karthik": {
        "name": "Karthik Iyer",
        "profile": (
            "Senior Software Engineer, Google. 9 YoE. IIT Madras CS, 6 years at Google (Search infra), "
            "previously Microsoft, frequent open-source contributor."
        ),
        "intent": "Looking at AI engineering — what's your AI program like for someone like me?",
        "linkedin": "IIT Madras CS, 6 years at Google Search infra, previously Microsoft, open-source contributor",
        "lead_whatsapp": "+919876543212",
        "transcript": (
            "BDA: Karthik, thanks for your time. Tell me what got you interested in Scaler. "
            "Karthik: Honestly, I'm exploring. I already work at Google. I can read the papers. "
            "I just want to make sure I'm not missing anything on the applied side. "
            "BDA: Of course. What would you want to learn? "
            "Karthik: My real question is — what would I actually learn here that I can't pick up from papers "
            "or internal training? I need to be honest about that before I commit. "
            "BDA: Our curriculum is very hands-on — "
            "Karthik: Also — is your cohort going to be at my level? Because if I'm tutoring everyone, "
            "I'm not getting value. BDA: We have senior folks, yeah. "
            "Karthik: Last one — are your instructors people who've actually shipped production AI systems, "
            "or is it academic? I've sat through enough academic ML."
        ),
    },
    "meera": {
        "name": "Meera Patel",
        "profile": (
            "Final-year B.Tech, Tier-3 college, 0 YoE. Got a government job offer through campus. "
            "Parents want her to take it."
        ),
        "intent": "Need a job, family wants me to take the govt job offer but I want to work at a product company",
        "linkedin": "None provided",
        "lead_whatsapp": "+919876543213",
        "transcript": (
            "BDA: Meera, tell me what's on your mind. "
            "Meera: I'm in my final year. I got a government job offer through campus. My parents want me "
            "to take it. But I want to work at a product company. I'm confused. "
            "BDA: I understand. How can we help? "
            "Meera: The first thing my parents are going to ask is — can you guarantee I'll get a job "
            "after this? Because if I don't, I've turned down a secure government job for nothing. "
            "BDA: We have strong placement — "
            "Meera: And Rs.3.5L is more than what my family earns in a year. I genuinely don't know "
            "how people afford this. How does that work? BDA: We have financing options. "
            "Meera: Also — I'm nervous about your entrance test. What if I can't clear it? "
            "Does that mean I'm not right for this?"
        ),
    },
}


def _apply_theme() -> None:
    st.markdown(
        """
<style>
/* Sidebar */
section[data-testid="stSidebar"] {
  background: #1a1a2e !important;
}
section[data-testid="stSidebar"] * {
  color: #e8e8ed !important;
}
section[data-testid="stSidebar"] .stMarkdown, section[data-testid="stSidebar"] label {
  color: #e8e8ed !important;
}

/* Main app */
.block-container {
  padding-top: 1.25rem;
  padding-bottom: 3rem;
  max-width: 1200px;
}
.stApp {
  background-color: #f4f4f6;
}

/* Typography */
.main h1 { font-size: 1.75rem; }
.main h2 { font-size: 1.35rem; }
.main .stCaption, .main [data-testid="stMarkdownContainer"] p { font-size: 0.98rem; }

/* Accent elements */
.hero-wrap {
  background: linear-gradient(120deg, #1a1a2e, #252542);
  border-radius: 14px;
  padding: 20px;
  margin-bottom: 14px;
  color: #f8fafc;
  border-left: 4px solid #e67e22;
}
.hero-sub { color: #cfd4e8; margin-top: 6px; font-size: 1rem; }

/* Cards */
.card {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #ffffff;
  padding: 16px;
  box-shadow: 0 6px 18px rgba(26,26,46,0.07);
}

/* PDF approval shell */
.pdf-approve-box {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 20px;
  margin-top: 14px;
  box-shadow: 0 8px 24px rgba(26,26,46,0.08);
}

/* Buttons */
.stButton > button {
  border-radius: 10px !important;
  font-weight: 600 !important;
}
button[kind="primary"] {
  background-color: #e67e22 !important;
  border-color: #c86a18 !important;
  color: #ffffff !important;
}
button[kind="secondary"] {
  background-color: #2563eb !important;
  border-color: #1d4ed8 !important;
  color: #ffffff !important;
}

/* Approve row: middle edit neutral, third skip muted (secondary used for send elsewhere) */
</style>
""",
        unsafe_allow_html=True,
    )


def _init_session() -> None:
    defaults: dict[str, Any] = {
        "nudge_text": "",
        "nudge_generated": False,
        "nudge_last_sid": None,
        "post_pdf_bytes": None,
        "post_pdf_path": None,
        "post_questions": [],
        "post_extract": None,
        "post_transcript_display": "",
        "post_cover_message": "",
        "post_payload_title": "",
        "post_ready": False,
        "post_awaiting_approval": False,
        "post_last_error": None,
        "post_last_twilio_sid": None,
        "post_status_message": "",
        "post_pdf_attachment_missed": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _set_preset(prefix: str, key: str, *, include_transcript: bool) -> None:
    p = PRESETS[key]
    st.session_state[f"{prefix}_name"] = p["name"]
    st.session_state[f"{prefix}_profile"] = p["profile"]
    st.session_state[f"{prefix}_intent"] = p["intent"]
    if prefix == "nudge":
        st.session_state["nudge_linkedin"] = p["linkedin"]
    if include_transcript:
        st.session_state["post_input_mode"] = "Text Transcript"
        st.session_state["post_transcript"] = p["transcript"]
        demo = os.environ.get("DEMO_LEAD_WHATSAPP", "").strip()
        wa = demo or str(p.get("lead_whatsapp", "")).strip()
        if wa:
            st.session_state["post_lead_whatsapp"] = wa


def _post_build_profile() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, label in (
        ("post_name", "Name"),
        ("post_profile", "Profile / background"),
        ("post_intent", "Intent"),
        ("post_lead_whatsapp", "Lead WhatsApp"),
    ):
        val = (st.session_state.get(key) or "").strip()
        if val:
            out[label] = val
    return out


def _reset_post_flow(*, clear_transcript_widgets: bool = False) -> None:
    st.session_state["post_pdf_bytes"] = None
    st.session_state["post_pdf_path"] = None
    st.session_state["post_questions"] = []
    st.session_state["post_extract"] = None
    if clear_transcript_widgets:
        st.session_state["post_transcript_display"] = ""
    st.session_state["post_cover_message"] = ""
    st.session_state["post_payload_title"] = ""
    st.session_state["post_ready"] = False
    st.session_state["post_awaiting_approval"] = False
    st.session_state["post_last_twilio_sid"] = None
    st.session_state["post_last_error"] = None
    st.session_state["post_status_message"] = ""
    st.session_state["post_pdf_attachment_missed"] = False


def _copy_button(text: str, key: str) -> None:
    _ = key
    js_lit = json.dumps(text)
    components.html(
        f"""
<button type="button" style="padding:10px 14px;border-radius:10px;border:1px solid #cbd5e1;background:#f8fafc;cursor:pointer;font-weight:600;width:100%;"
onclick='navigator.clipboard.writeText({js_lit})'>
Copy to Clipboard
</button>
""",
        height=48,
    )


def main() -> None:
    st.set_page_config(page_title="Scaler BDA Agent", page_icon="🚀", layout="wide")
    _init_session()

    # Defer post-flow reset to start of run so we never write widget-bound keys after those widgets render.
    if st.session_state.pop("_flush_post_flow_skip", False):
        _reset_post_flow(clear_transcript_widgets=True)
        st.session_state["_show_skip_done"] = True

    _apply_theme()

    st.markdown(
        '<div class="hero-wrap"><h1 style="margin:0;">Scaler BDA Agent</h1>'
        '<div class="hero-sub">Pre-call briefs &amp; post-call PDF follow-ups</div></div>',
        unsafe_allow_html=True,
    )

    if st.session_state.pop("_show_skip_done", False):
        st.success("Skipped. Draft cleared.")

    with st.sidebar:
        st.header("Onboarding")
        st.text_input(
            "Evaluator phone number",
            key="evaluator_whatsapp",
            placeholder="+91...",
            help="Pre-sales WhatsApp lands here.",
        )
        st.text_input("BDA name", key="bda_name", placeholder="e.g. Neha")
        st.divider()
        st.header("API Status")
        for env_key, label in REQUIRED_ENV:
            ok_e = bool(os.environ.get(env_key, "").strip())
            st.caption(f"{label}: {'OK | set' if ok_e else '-- | missing'}")
        wo = bool(os.environ.get("OPENAI_API_KEY", "").strip())
        st.caption(f"Whisper (OpenAI): {'OK | set' if wo else '-- | missing'}")
        pu = bool(os.environ.get("STATIC_PUBLIC_BASE_URL", "").strip()) or (
            bool(os.environ.get("TWILIO_PUBLIC_MEDIA_PATH", "").strip())
            and bool(os.environ.get("TWILIO_PUBLIC_MEDIA_URL", "").strip())
        )
        st.caption(
            f"Public PDF URL: {'OK | configured' if pu else '-- | needs STATIC_PUBLIC_BASE_URL or TWILIO_PUBLIC_*'}"
        )
        if not pu:
            with st.expander("Why PDF may not attach on WhatsApp"):
                st.markdown(PDF_ATTACHMENT_SETUP)
        if st.button("Test Twilio Auth", use_container_width=True):
            try:
                sid = test_twilio_auth()
                st.success(f"Twilio auth OK for account `{sid}`.")
            except Exception as e:
                st.error(str(e))
        with st.expander("How to use"):
            st.markdown(
                "- Set evaluator WhatsApp\n"
                "- Presets demo three personas\n"
                "- Post-call: preview then Approve / Edit / Skip\n"
                "- Secrets in `.env`"
            )
        st.caption(f"App version `{APP_VERSION}`")

    tab_nudge, tab_pdf = st.tabs(["Pre-Sales Nudge", "Post-Call PDF"])

    with tab_nudge:
        st.subheader("Pre-Sales Nudge")
        pn1, pn2, pn3 = st.columns(3)
        if pn1.button(
            f"{chr(0x1F4CB)} Load Rohan (TCS, 4 YoE)", use_container_width=True, key="nudge_pre_ro"
        ):
            _set_preset("nudge", "rohan", include_transcript=False)
        if pn2.button(
            f"{chr(0x1F4CB)} Load Karthik (Google, 9 YoE)", use_container_width=True, key="nudge_pre_ka"
        ):
            _set_preset("nudge", "karthik", include_transcript=False)
        if pn3.button(
            f"{chr(0x1F4CB)} Load Meera (Student, 0 YoE)", use_container_width=True, key="nudge_pre_me"
        ):
            _set_preset("nudge", "meera", include_transcript=False)

        st.text_input("Lead name", key="nudge_name")
        st.text_area("Profile / background", key="nudge_profile", height=120)
        st.text_input("Intent", key="nudge_intent")
        st.text_area("LinkedIn info", key="nudge_linkedin", height=80)

        c1, c2 = st.columns(2)
        gen_nudge = c1.button("Generate Nudge", type="primary", use_container_width=True)
        send_nudge = c2.button("Send to WhatsApp", type="secondary", use_container_width=True)

        if gen_nudge:
            try:
                if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
                    raise ValueError("ANTHROPIC_API_KEY is not set.")
                st.session_state["nudge_text"] = generate_pre_sales_nudge(
                    bda_name=(st.session_state.get("bda_name") or "").strip(),
                    lead_profile={},
                    name=(st.session_state.get("nudge_name") or "").strip() or None,
                    profile=(st.session_state.get("nudge_profile") or "").strip() or None,
                    intent=(st.session_state.get("nudge_intent") or "").strip() or None,
                    linkedin_background=(st.session_state.get("nudge_linkedin") or "").strip() or None,
                )
                st.session_state["nudge_generated"] = True
            except Exception as e:
                st.error(str(e))
                with st.expander("Error details"):
                    st.code(traceback.format_exc())

        nudge_text = (st.session_state.get("nudge_text") or "").strip()
        if nudge_text:
            st.markdown(
                '<div class="card"><div class="mono-block" style="font-family:Segoe UI,Arial,sans-serif;white-space:pre-wrap;line-height:1.5;">'
                + html_lib.escape(nudge_text)
                + "</div></div>",
                unsafe_allow_html=True,
            )
            st.caption(f"Characters: {len(nudge_text)}")
            nc1, nc2 = st.columns([2, 1])
            with nc1:
                st.button("Send to WhatsApp (again)", key="send_secondary", use_container_width=True, type="secondary")
            with nc2:
                _copy_button(nudge_text, "copy_nudge")

        if send_nudge or st.session_state.get("send_secondary"):
            try:
                to = (st.session_state.get("evaluator_whatsapp") or "").strip()
                if not to:
                    raise ValueError("Add evaluator phone in sidebar.")
                if not nudge_text:
                    raise ValueError("Generate or paste nudge text first.")
                sid = send_text_message(to, nudge_text)
                st.session_state["nudge_last_sid"] = sid
                st.success(f"Sent. Twilio SID: `{sid}`")
            except Exception as e:
                st.error(str(e))
                with st.expander("Error details"):
                    st.code(traceback.format_exc())

    with tab_pdf:
        st.subheader("Post-Call PDF")
        pp1, pp2, pp3 = st.columns(3)
        if pp1.button(
            f"{chr(0x1F4CB)} Load Rohan (TCS, 4 YoE)", use_container_width=True, key="post_pre_ro"
        ):
            _set_preset("post", "rohan", include_transcript=True)
        if pp2.button(
            f"{chr(0x1F4CB)} Load Karthik (Google, 9 YoE)", use_container_width=True, key="post_pre_ka"
        ):
            _set_preset("post", "karthik", include_transcript=True)
        if pp3.button(
            f"{chr(0x1F4CB)} Load Meera (Student, 0 YoE)", use_container_width=True, key="post_pre_me"
        ):
            _set_preset("post", "meera", include_transcript=True)

        post_mode = st.radio(
            "Input",
            ["Text Transcript", "Audio Upload"],
            horizontal=True,
            key="post_input_mode",
        )
        if post_mode == "Text Transcript":
            st.text_area("Call transcript", key="post_transcript", height=220)
        else:
            st.file_uploader(
                "Audio recording",
                type=["mp3", "wav", "m4a", "mp4", "webm"],
                key="post_audio",
                help="Approx. max 25 MB (Whisper).",
            )

        st.text_input("Lead name", key="post_name")
        st.text_area("Profile", key="post_profile", height=100)
        st.text_input("Intent", key="post_intent")
        st.text_input(
            "Lead WhatsApp",
            key="post_lead_whatsapp",
            placeholder="+91... or whatsapp:+14155238886 (sandbox)",
            help="Required before Approve & Send. Presets fill a demo number; set DEMO_LEAD_WHATSAPP in .env to use your test recipient.",
        )
        persona = st.selectbox(
            "PDF template",
            ["Auto (from call)", "Career switcher", "Senior professional", "Newcomer / student"],
            key="post_persona",
        )

        if st.button("Generate PDF", type="primary", use_container_width=True, key="btn_gen_pdf"):
            try:
                _reset_post_flow(clear_transcript_widgets=False)
                profile = _post_build_profile()
                lead_name = (
                    (st.session_state.get("post_name") or "").strip() or profile.get("Name", "there")
                )
                bda = (st.session_state.get("bda_name") or "").strip() or "Your BDA"
                with st.status("Generating your PDF...", expanded=True) as status:
                    if post_mode == "Audio Upload":
                        status.write(f"{chr(0x1F3A4)} Transcribing audio...")
                        if not os.environ.get("OPENAI_API_KEY", "").strip():
                            raise ValueError("OPENAI_API_KEY required for Whisper.")
                        upload = st.session_state.get("post_audio")
                        if upload is None:
                            raise ValueError("Upload an audio file or switch to transcript.")
                        transcript_text = transcribe_audio(
                            audio_file=io.BytesIO(upload.getvalue()),
                            filename=upload.name or "audio.mp3",
                        )
                    else:
                        transcript_text = (st.session_state.get("post_transcript") or "").strip()
                        if not transcript_text:
                            raise ValueError("Paste transcript or use audio.")

                    status.write(f"{chr(0x1F50D)} Extracting insights from call...")
                    st.session_state["post_transcript_display"] = transcript_text
                    extracted = extract_transcript_insights(transcript=transcript_text, lead_profile=profile)
                    st.session_state["post_extract"] = extracted
                    st.session_state["post_questions"] = extracted.get("open_questions", [])

                    status.write(f"{chr(0x270D)} Generating personalized content...")
                    template_slug = (
                        extracted["persona_type"]
                        if persona == "Auto (from call)"
                        else persona_ui_label_to_slug(persona)
                    )
                    payload = generate_pdf_content(
                        lead_profile=profile,
                        transcript_extract=extracted,
                        bda_name=str(bda),
                        lead_name=str(lead_name),
                        scaler_data=get_facts_block(),
                        template_persona_slug=template_slug,
                    )

                    status.write(f"{chr(0x1F4C4)} Rendering PDF...")
                    layout_slug = (
                        payload.get("persona_type", template_slug)
                        if persona == "Auto (from call)"
                        else template_slug
                    )
                    tpl_name = template_for_persona_slug(layout_slug)
                    pdf_path = render_pdf(
                        tpl_name,
                        {
                            "name": str(lead_name),
                            "date": date.today().strftime("%d %b %Y"),
                            "greeting": payload["greeting"],
                            "cta_text": payload["cta_text"],
                            "sections": payload["sections"],
                        },
                    )
                    st.session_state["post_pdf_path"] = pdf_path
                    st.session_state["post_pdf_bytes"] = Path(pdf_path).read_bytes()
                    st.session_state["post_payload_title"] = f"{lead_name.strip() or 'Lead'} - brief"
                    st.session_state["post_cover_message"] = payload["covering_message"]
                    st.session_state["post_ready"] = True
                    st.session_state["post_awaiting_approval"] = True
                    status.update(label="PDF ready!", state="complete")
                st.success("Review the PDF and covering message - then Approve, Edit, or Skip.")
            except Exception as e:
                st.session_state["post_last_error"] = str(e)
                st.error(str(e))
                with st.expander("Error details"):
                    st.code(traceback.format_exc())

        if st.session_state.get("post_extract"):
            ex = st.session_state["post_extract"]
            with st.expander("Extracted insights", expanded=False):
                st.markdown(f"Persona type: `{ex.get('persona_type', '')}`")
                st.markdown("**Open questions**")
                for q in ex.get("open_questions", []):
                    st.markdown(f"- {q}")
                st.markdown("**Emotional drivers**")
                st.write(ex.get("emotional_drivers", ""))

        if st.session_state.get("post_pdf_bytes") and st.session_state.get("post_awaiting_approval"):
            st.markdown("##### Download & send")
            st.download_button(
                label="Download PDF",
                data=st.session_state["post_pdf_bytes"],
                file_name="scaler-lead-brief.pdf",
                mime="application/pdf",
                key="dl_pdf_prominent",
                type="primary",
                use_container_width=True,
            )
            try:
                st.pdf(io.BytesIO(st.session_state["post_pdf_bytes"]))
            except Exception:
                st.caption("Use Download if embedded preview fails.")
            st.text_area(
                "Covering WhatsApp message",
                key="post_cover_message",
                height=140,
                help="Editable before send.",
            )
            st.caption(
                f"Characters: {len((st.session_state.get('post_cover_message') or '').strip())}"
            )
            ba1, ba2, ba3 = st.columns(3)
            with ba1:
                approve = st.button(
                    f"{chr(0x2705)} Approve & Send to WhatsApp",
                    type="primary",
                    use_container_width=True,
                    key="btn_pdf_approve",
                )
            with ba2:
                edit_hint = st.button(
                    f"{chr(0x270F)} Edit",
                    use_container_width=True,
                    key="btn_pdf_edit",
                )
            with ba3:
                skip = st.button(
                    f"{chr(0x23ED)} Skip",
                    use_container_width=True,
                    key="btn_pdf_skip",
                )

            if edit_hint:
                st.info("Update the covering message or regenerate PDF, then Approve & Send.")

            if skip:
                st.session_state["_flush_post_flow_skip"] = True
                st.rerun()

            if approve:
                try:
                    lead_wa = (st.session_state.get("post_lead_whatsapp") or "").strip()
                    cover = (st.session_state.get("post_cover_message") or "").strip()
                    if not lead_wa:
                        st.error(
                            "Lead WhatsApp is empty. Enter the lead's number in **Lead WhatsApp** above "
                            "(country code required). For Twilio sandbox, use the WhatsApp number you joined with."
                        )
                        st.stop()
                    if not cover:
                        st.error("Covering message is empty. Add text in **Covering WhatsApp message** above.")
                        st.stop()
                    pdf_path = st.session_state.get("post_pdf_path")
                    fname = Path(pdf_path).name if pdf_path else None
                    pdf_url = static_pdf_url(fname) if fname else None
                    st.session_state["post_pdf_attachment_missed"] = False
                    if pdf_url:
                        sid = send_pdf_message(lead_wa, cover, pdf_url)
                        st.session_state["post_status_message"] = f"WhatsApp sent with PDF attachment. SID `{sid}`"
                    else:
                        result = send_whatsapp_with_optional_pdf(
                            to_number=lead_wa,
                            body=cover,
                            pdf_bytes=st.session_state.get("post_pdf_bytes"),
                        )
                        sid = result["sid"]
                        had_pdf = bool(result.get("had_attachment"))
                        st.session_state["post_pdf_attachment_missed"] = not had_pdf
                        if had_pdf:
                            st.session_state["post_status_message"] = (
                                f"WhatsApp sent with PDF. SID `{sid}`"
                            )
                        else:
                            st.session_state["post_status_message"] = (
                                f"WhatsApp sent (covering text only; PDF not attached). SID `{sid}`"
                            )
                    st.session_state["post_last_twilio_sid"] = sid
                    st.session_state["post_awaiting_approval"] = False
                    if st.session_state.get("post_pdf_attachment_missed"):
                        st.success("Approved — WhatsApp message delivered.")
                        st.warning(PDF_ATTACHMENT_SETUP)
                    else:
                        st.success("Approved and sent.")
                except Exception as e:
                    st.error(str(e))
                    with st.expander("Error details"):
                        st.code(traceback.format_exc())

        elif st.session_state.get("post_pdf_bytes"):
            st.download_button(
                "Download PDF",
                data=st.session_state["post_pdf_bytes"],
                file_name="scaler-lead-brief.pdf",
                mime="application/pdf",
                key="dl_pdf_after_send",
            )
            try:
                st.pdf(io.BytesIO(st.session_state["post_pdf_bytes"]))
            except Exception:
                pass

        if st.session_state.get("post_status_message"):
            st.info(st.session_state["post_status_message"])


if __name__ == "__main__":
    main()

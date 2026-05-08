# Scaler BDA AI Assistant

Streamlit app for Business Development Associates: **pre-sales WhatsApp nudges** (auto-send to the BDA) and **post-call PDF briefs** (send to the lead’s WhatsApp after approval).

## Features

1. **Pre-Sales Nudge** — Lead profile → Claude generates a short, scannable WhatsApp briefing → sent to the **evaluator / BDA WhatsApp** via Twilio (no approval step).
2. **Post-Call PDF** — Profile + transcript (text or audio) → Whisper transcription if needed → Claude extracts open questions → Claude drafts PDF sections grounded in `utils/scaler_data.py` → WeasyPrint renders one of three HTML templates → editable covering message → **Approve / Edit / Skip**; **Approve** sends to the **lead’s** WhatsApp.

## Stack

- **UI:** Streamlit  
- **LLM:** Anthropic Claude `claude-3-5-sonnet-latest`
- **Speech-to-text:** OpenAI Whisper API  
- **PDF:** Jinja2 HTML templates + WeasyPrint  
- **Messaging:** Twilio WhatsApp (sandbox or production)

## Setup

### 1. Python environment

```bash
cd scaler-bda-agent
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. WeasyPrint system dependencies

WeasyPrint needs GTK/Pango/cairo installed at the OS level.

- **Windows:** install the [official WeasyPrint Windows bundles](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation) or follow their GTK guidance; restart the terminal after installing.  
- **macOS:** `brew install pango gdk-pixbuf libffi` (see WeasyPrint docs for your version).  
- **Linux:** use your distro’s `pango`, `cairo`, etc., per WeasyPrint docs.

If WeasyPrint fails to import, the app will surface a clear error when generating a PDF.

### 3. Environment variables

Copy `.env.example` to `.env` and fill in keys:

```bash
copy .env.example .env
```

At minimum:

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY` (audio path)
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`

Use your Twilio **WhatsApp Sandbox** join flow so both your test numbers can message the sandbox number.

### 4. Optional: PDF attachment on WhatsApp

Twilio requires a **public HTTPS URL** for `media_url`. For local experiments you can:

- Upload PDFs to cloud storage and set a predictable URL pattern, **or**
- Serve a folder over HTTPS (e.g. tunnel + static host) and set:

  - `TWILIO_PUBLIC_MEDIA_PATH` — directory the app can **write** PDFs into  
  - `TWILIO_PUBLIC_MEDIA_URL` — HTTPS base URL that serves those files  

If these are unset, **Approve** still sends the **text** of the covering message; the UI shows a warning that the PDF was not attached. Leads can still use the in-app **Download PDF** button when the BDA shares the session, or you can paste a link manually in your workflow.

## Run

From `scaler-bda-agent`:

```bash
streamlit run app.py
```

## Project layout

```
scaler-bda-agent/
├── app.py
├── agents/
│   ├── nudge_generator.py
│   ├── pdf_content_generator.py
│   ├── transcript_extractor.py
│   └── audio_transcriber.py
├── utils/
│   ├── whatsapp.py
│   ├── pdf_renderer.py
│   └── scaler_data.py
├── templates/
│   ├── career_switcher.html
│   ├── senior_professional.html
│   └── newcomer_student.html
├── requirements.txt
├── .env.example
└── README.md
```

## Program facts

`utils/scaler_data.py` holds **curated** copy for Claude to ground PDF answers. Keep it aligned with live collateral; do not rely on the model to invent policies, fees, or guarantees.

## Security notes

- Never commit `.env` or real API keys.  
- Twilio sandbox is for development; production requires WhatsApp Sender approval and compliance with Meta/Twilio policies.  
- PDF HTML is sanitized lightly; prefer facts from `scaler_data` and review generated PDFs before approval.

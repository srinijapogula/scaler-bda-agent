## What I built

An AI-powered BDA assistant that generates pre-call WhatsApp nudges and post-call personalized PDFs for Scaler's sales team. Takes a lead profile and call transcript (text or audio), extracts open questions using Claude, generates a persona-specific PDF with grounded Scaler curriculum data, and delivers everything via WhatsApp through Twilio. Built with Streamlit, Claude API, OpenAI Whisper, WeasyPrint, and Twilio. Every lead-facing message goes through a BDA approval gate before sending.

## One failure I found

When leads ask hyper-specific curriculum questions (e.g. "which exact LLM framework versions do you cover?"), the agent occasionally generates plausible-sounding but unverifiable claims despite grounding instructions. A production fix would be RAG over scaler.com with automated re-indexing, the current static data file covers 80% of cases but misses edge cases.

## Scale plan

At 100K leads/month, two things break: LLM latency (each PDF needs 2 API calls at 3-5s each, capping throughput at ~500/day sequentially) and WhatsApp rate limits (sandbox allows only opted-in numbers). Fix: async queue with Celery/Redis for parallel LLM calls and PDF rendering, migrate from Twilio Sandbox to WhatsApp Business API via a BSP like Gupshup, and replace the static curriculum data file with a RAG pipeline over scaler.com for real-time grounding.

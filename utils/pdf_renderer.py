"""Render HTML templates to PDF with Jinja2 + WeasyPrint."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

try:
    from weasyprint import HTML
except Exception as e:  # ImportError, OSError (missing GTK/Pango on some Windows installs), etc.
    HTML = None  # type: ignore
    _WEASYPRINT_IMPORT_ERROR = e
else:
    _WEASYPRINT_IMPORT_ERROR = None


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _templates_dir() -> Path:
    return _project_root() / "templates"


def _static_dir() -> Path:
    d = _project_root() / "static"
    d.mkdir(parents=True, exist_ok=True)
    return d


def static_dir() -> Path:
    """Public PDFs directory (for HTTP servers / Twilio media URLs)."""
    return _static_dir()


def static_pdf_url(filename: str) -> str | None:
    """
    Build public URL for a file in ``static/`` if ``STATIC_PUBLIC_BASE_URL`` is set.

    Example env: ``STATIC_PUBLIC_BASE_URL=https://example.com/static``
    """
    base = os.environ.get("STATIC_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base:
        return None
    name = Path(filename).name
    return f"{base}/{name}"


def _render_html(template_name: str, context_data: dict[str, Any]) -> str:
    tpl_dir = _templates_dir()
    if not tpl_dir.is_dir():
        raise FileNotFoundError(f"Templates directory not found: {tpl_dir}")

    env = Environment(
        loader=FileSystemLoader(str(tpl_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(template_name)
    return template.render(**context_data)


def _validate_html_for_pdf(html_str: str, template_name: str) -> None:
    """Ensure a full HTML document for WeasyPrint: DOCTYPE + html + head (with style) + body."""
    trimmed = html_str.lstrip("\ufeff")
    if "<!DOCTYPE" not in trimmed[:200]:
        raise RuntimeError(
            f"Template `{template_name}` missing <!DOCTYPE html>. Expected a complete HTML document for PDF."
        )
    if not re.search(r"(?is)<html\b.*?>", trimmed):
        raise RuntimeError(f"Template `{template_name}` missing `<html>` root element.")
    if not re.search(r"(?is)<head\b.*?>.*?</head>", trimmed):
        raise RuntimeError(f"Template `{template_name}` missing `<head>...</head>`.")
    if not re.search(r"(?is)<head\b.*?<style\b.*?>.*?</style>", trimmed):
        raise RuntimeError(
            f"Template `{template_name}`: all CSS must be inside `<style>` within `<head>`."
        )
    if not re.search(r"(?is)<body\b.*?>.*?</body>", trimmed):
        raise RuntimeError(f"Template `{template_name}` missing `<body>...</body>`.")
    if re.search(r"(?is)</head>\s*<style\b", trimmed):
        raise RuntimeError(
            f"Template `{template_name}`: `<style>` must not appear after `</head>` (avoids CSS as body text)."
        )


def _render_with_weasyprint(html_str: str) -> bytes:
    tpl_dir = _templates_dir()
    base_url = tpl_dir.as_uri() + "/"
    # Pass explicit UTF-8 document so meta charset and content stay aligned.
    doc = HTML(string=html_str, base_url=base_url)
    return doc.write_pdf()


def _render_with_reportlab(html_str: str) -> bytes:
    """
    Fallback PDF renderer for environments without GTK/Pango (e.g., local Windows).
    It strips HTML to readable text and builds a basic PDF.
    """
    # Remove non-body content so CSS/JS is never emitted as visible text.
    text = re.sub(r"(?is)<head.*?>.*?</head>", "", html_str)
    text = re.sub(r"(?is)<style.*?>.*?</style>", "", text)
    text = re.sub(r"(?is)<script.*?>.*?</script>", "", text)

    # Keep some line breaks before stripping remaining tags.
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=40,
        bottomMargin=40,
    )
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    body.fontSize = 10
    body.leading = 14

    story = []
    for ln in lines:
        story.append(Paragraph(ln.replace("&", "&amp;"), body))
        story.append(Spacer(1, 6))
    if not story:
        story = [Paragraph("No content generated.", body)]
    doc.build(story)
    return buf.getvalue()


def _render_pdf_bytes_from_html(html_str: str) -> bytes:
    if HTML is not None:
        return _render_with_weasyprint(html_str)
    return _render_with_reportlab(html_str)


def render_pdf(template_name: str, context_data: dict[str, Any]) -> str:
    """
    Render ``templates/{template_name}`` with Jinja2, convert to PDF via WeasyPrint.

    Writes:
    - A unique file under the system temp directory (returned path).
    - An identical copy under ``static/`` for public URL hosting.

    Returns:
        Absolute path to the temporary PDF file.
    """
    html_str = _render_html(template_name, context_data)
    _validate_html_for_pdf(html_str, template_name)
    pdf_bytes = _render_pdf_bytes_from_html(html_str)

    fname = f"scaler-brief-{uuid.uuid4().hex}.pdf"
    temp_path = Path(tempfile.gettempdir()) / fname
    temp_path.write_bytes(pdf_bytes)

    static_path = _static_dir() / fname
    shutil.copy2(temp_path, static_path)

    return str(temp_path.resolve())


def render_pdf_bytes(
    *,
    template_filename: str,
    context: dict[str, Any],
    base_url: str | None = None,
) -> bytes:
    """
    Render template to PDF bytes (in-memory). Does not write ``static/`` or temp files.

    Prefer :func:`render_pdf` when Twilio needs a stable on-disk file in ``static/``.
    """
    # base_url retained for signature compatibility; not needed by reportlab fallback.
    _ = base_url
    html_str = _render_html(template_filename, context)
    _validate_html_for_pdf(html_str, template_filename)
    return _render_pdf_bytes_from_html(html_str)

"""Conversione Markdown -> HTML per il pannello risposta e per i report esportati."""

from __future__ import annotations

import html
import re
from datetime import datetime

import markdown

_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")
_EXTENSIONS = ["tables", "fenced_code", "sane_lists", "attr_list"]

THEMES = {
    "dark": {"bg": "#2b2b2b", "fg": "#e3e3e3", "muted": "#a0a0a0", "accent": "#5aa9ff",
             "border": "#474747", "th": "#363d48", "zebra": "#303030", "code": "#1e1e1e",
             "quote": "#3a3320"},
    "light": {"bg": "#ffffff", "fg": "#1d1d1f", "muted": "#666666", "accent": "#1f6fd1",
              "border": "#d0d4da", "th": "#eaf1fb", "zebra": "#f7f8fa", "code": "#f3f4f6",
              "quote": "#fff7e0"},
}


def normalize_markdown(text: str) -> str:
    """Rende il Markdown tipico degli LLM compatibile con Python-Markdown.

    Python-Markdown richiede una riga vuota prima di elenchi e tabelle e
    un rientro di 4 spazi per gli elenchi annidati.
    """
    out: list[str] = []
    prev = ""
    in_code = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            if not in_code and prev.strip():
                out.append("")
            in_code = not in_code
            out.append(line)
            prev = line
            continue
        if not in_code:
            m = _LIST_RE.match(line)
            if m and 0 < len(m.group(1)) < 4:
                line = "    " + line.lstrip()
            is_list = bool(m)
            is_table = line.lstrip().startswith("|")
            prev_list = bool(_LIST_RE.match(prev))
            prev_table = prev.lstrip().startswith("|")
            if prev.strip() and ((is_list and not prev_list and not prev.startswith(" "))
                                 or (is_table and not prev_table)):
                out.append("")
        out.append(line)
        prev = line
    return "\n".join(out)


def md_to_html_body(text: str) -> str:
    return markdown.markdown(normalize_markdown(text), extensions=_EXTENSIONS, output_format="html")


def _css(theme: str, font_px: int) -> str:
    c = THEMES[theme]
    return f"""
    body {{ background:{c['bg']}; color:{c['fg']}; font-family:'Segoe UI', Arial, sans-serif;
            font-size:{font_px}px; line-height:1.5; margin:14px 18px; }}
    h1, h2, h3, h4 {{ color:{c['accent']}; margin:16px 0 6px 0; }}
    h1 {{ font-size:{int(font_px*1.6)}px; }} h2 {{ font-size:{int(font_px*1.35)}px; }}
    h3 {{ font-size:{int(font_px*1.15)}px; }} h4 {{ font-size:{font_px}px; }}
    p {{ margin:6px 0; }}
    a {{ color:{c['accent']}; }}
    table {{ border-collapse:collapse; margin:10px 0; }}
    th, td {{ border:1px solid {c['border']}; padding:5px 10px; vertical-align:top; }}
    th {{ background:{c['th']}; font-weight:bold; text-align:left; }}
    tr:nth-child(even) td {{ background:{c['zebra']}; }}
    code {{ font-family:Consolas, monospace; background:{c['code']}; padding:1px 4px; }}
    pre {{ background:{c['code']}; padding:10px; border:1px solid {c['border']}; white-space:pre-wrap; }}
    pre code {{ padding:0; }}
    blockquote {{ background:{c['quote']}; border-left:4px solid #e0a800; margin:8px 0;
                  padding:6px 12px; }}
    hr {{ border:0; border-top:1px solid {c['border']}; margin:14px 0; }}
    ul, ol {{ margin:4px 0 4px 22px; padding-left:8px; }}
    li {{ margin:2px 0; }}
    .muted {{ color:{c['muted']}; }}
    """


def render_panel_html(text: str, dark: bool, font_px: int = 14) -> str:
    theme = "dark" if dark else "light"
    return (f"<html><head><style>{_css(theme, font_px)}</style></head>"
            f"<body>{md_to_html_body(text)}</body></html>")


def render_report_html(text: str, prompt: str, provider: str, model: str, files: list[str]) -> str:
    when = datetime.now().strftime("%d/%m/%Y %H:%M")
    files_html = ", ".join(html.escape(f) for f in files) or "nessuno"
    extra = """
    body { max-width: 980px; margin: 32px auto; padding: 0 24px; }
    header { border-bottom: 3px solid #1f6fd1; padding-bottom: 10px; margin-bottom: 18px; }
    header h1 { margin: 0; color: #12355b; }
    .meta { font-size: 13px; color: #555; margin-top: 6px; }
    .prompt { background: #f3f6fa; border: 1px solid #d0d4da; padding: 10px 14px; white-space: pre-wrap; }
    footer { margin-top: 30px; border-top: 1px solid #d0d4da; padding-top: 8px; font-size: 12px; color: #777; }
    @media print { body { margin: 0; max-width: none; } a { color: inherit; } }
    """
    return f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8">
<title>Report Smart CFO Assistant – {when}</title>
<style>{_css('light', 15)}{extra}</style></head>
<body>
<header>
  <h1>Smart CFO Assistant – Report</h1>
  <div class="meta">Data: {when} · Motore: {html.escape(provider)} · Modello: {html.escape(model)}<br>
  Documenti: {files_html}</div>
</header>
<h2>Richiesta</h2>
<div class="prompt">{html.escape(prompt)}</div>
<h2>Risposta</h2>
{md_to_html_body(text)}
<footer>Documento generato con l'ausilio dell'intelligenza artificiale: verificare i dati
prima dell'utilizzo per finalità contabili, fiscali o decisionali.</footer>
</body></html>"""


def render_report_markdown(text: str, prompt: str, provider: str, model: str, files: list[str]) -> str:
    when = datetime.now().strftime("%d/%m/%Y %H:%M")
    return (f"# Smart CFO Assistant – Report\n\n"
            f"- **Data:** {when}\n- **Motore:** {provider}\n- **Modello:** {model}\n"
            f"- **Documenti:** {', '.join(files) or 'nessuno'}\n\n"
            f"## Richiesta\n\n{prompt}\n\n## Risposta\n\n{text}\n")

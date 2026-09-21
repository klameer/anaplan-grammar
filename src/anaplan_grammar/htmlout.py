"""Render the review Markdown as a self-contained HTML page. A small
converter for the Markdown this package emits (headings, paragraphs,
bullet and numbered lists, tables, bold, inline code, fenced mermaid),
so the page is the tool's output and not a hand-copied version of it."""
from __future__ import annotations
import html, re

CSS = """
:root{--bg:#F7F8F6;--ink:#1B2430;--muted:#5C6773;--rule:#D9DED9;--soft:#EEF1EE;--accent:#0E5E6F;--crit:#A6301C;--major:#B7791F;--minor:#4B6C8C;--info:#6B7A70;--bar:#0E5E6F;--bar-soft:#CFE0E3;
--serif:"Source Serif 4",Georgia,"Times New Roman",serif;--sans:"IBM Plex Sans","Helvetica Neue",Arial,sans-serif;--mono:"IBM Plex Mono",Consolas,"Courier New",monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141A1C;--ink:#E6EBE8;--muted:#9AA6A0;--rule:#2E393C;--soft:#222C2F;--accent:#5FB3C1;--crit:#E07A63;--major:#D9A441;--minor:#86A8C5;--info:#93A39A;--bar:#5FB3C1;--bar-soft:#2A4247}}
:root[data-theme="dark"]{--bg:#141A1C;--ink:#E6EBE8;--muted:#9AA6A0;--rule:#2E393C;--soft:#222C2F;--accent:#5FB3C1;--crit:#E07A63;--major:#D9A441;--minor:#86A8C5;--info:#93A39A;--bar:#5FB3C1;--bar-soft:#2A4247}
*{box-sizing:border-box}body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.55;margin:0}
.page{max-width:860px;margin:0 auto;padding:44px 28px 72px}
h1{font-family:var(--serif);font-weight:600;font-size:34px;line-height:1.15;margin:32px 0 6px;text-wrap:balance}
h1:first-child{margin-top:0}
h2{font-family:var(--serif);font-weight:600;font-size:21px;margin:40px 0 10px;text-wrap:balance}
h3{font-size:15px;font-weight:600;margin:22px 0 6px}
p{max-width:72ch;margin:8px 0}
.lead{color:var(--muted);font-size:13.5px}
table{border-collapse:collapse;width:100%;font-size:13.5px;margin:10px 0}
th{text-align:left;font-size:11.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:500;padding:8px 10px 8px 0;border-bottom:1px solid var(--rule)}
td{padding:7px 10px 7px 0;border-bottom:1px solid var(--rule);vertical-align:top}
td:last-child,th:last-child{padding-right:0}
.wrap{overflow-x:auto}
code{font-family:var(--mono);font-size:12.5px;background:var(--soft);padding:1px 4px;border-radius:2px}
ul,ol{max-width:72ch;padding-left:22px}li{margin:4px 0}
hr{border:0;border-top:1px solid var(--rule);margin:36px 0}
.ev{color:var(--muted);font-size:12.5px}
.ev code{font-size:11.5px}
pre.mermaid{background:transparent;overflow-x:auto}
strong{font-weight:600}
"""

HEAD = ('<title>{title}</title>\n'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">\n'
        '<style>{css}</style>\n<div class="page">\n')


def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"_([^_]+)_", r"<em>\1</em>", s)
    return s


def md_to_html(md: str, title: str) -> str:
    out = [HEAD.format(title=html.escape(title), css=CSS)]
    lines = md.split("\n")
    i = 0
    para: list[str] = []
    lst = None   # ("ul"|"ol", [items])

    def flush_para():
        nonlocal para
        if para:
            text = " ".join(para)
            cls = ' class="ev"' if text.startswith("Evidence:") else ' class="lead"' if text.startswith(("Generated ", "Written by ", "Scores are", "19 rules")) else ""
            out.append(f"<p{cls}>{_inline(text)}</p>")
            para = []

    def flush_list():
        nonlocal lst
        if lst:
            tag, items = lst
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
            lst = None

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```mermaid"):
            flush_para(); flush_list()
            j = i + 1; buf = []
            while j < len(lines) and not lines[j].startswith("```"):
                buf.append(lines[j]); j += 1
            out.append('<pre class="mermaid">' + html.escape("\n".join(buf), quote=False) + "</pre>")
            i = j + 1; continue
        if ln.startswith("```"):
            flush_para(); flush_list()
            j = i + 1; buf = []
            while j < len(lines) and not lines[j].startswith("```"):
                buf.append(lines[j]); j += 1
            out.append("<pre><code>" + html.escape("\n".join(buf), quote=False) + "</code></pre>")
            i = j + 1; continue
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            flush_para(); flush_list()
            hdr = [c.strip() for c in ln.strip("|").split("|")]
            j = i + 2; rows = []
            while j < len(lines) and lines[j].startswith("|"):
                rows.append([c.strip() for c in lines[j].strip("|").split("|")]); j += 1
            t = ['<div class="wrap"><table><tr>' + "".join(f"<th>{_inline(h)}</th>" for h in hdr) + "</tr>"]
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>")
            t.append("</table></div>")
            out.append("".join(t)); i = j; continue
        m = re.match(r"^(#{1,3})\s+(.*)", ln)
        if m:
            flush_para(); flush_list()
            lvl = len(m.group(1)); out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>"); i += 1; continue
        if ln.strip() == "---":
            flush_para(); flush_list(); out.append("<hr>"); i += 1; continue
        m = re.match(r"^(\s*)[-*]\s+(.*)", ln)
        if m:
            flush_para()
            if not lst or lst[0] != "ul": flush_list(); lst = ("ul", [])
            lst[1].append(("&nbsp;&nbsp;" * (len(m.group(1)) // 2)) + m.group(2)); i += 1; continue
        m = re.match(r"^\d+\.\s+(.*)", ln)
        if m:
            flush_para()
            if not lst or lst[0] != "ol": flush_list(); lst = ("ol", [])
            lst[1].append(m.group(1)); i += 1; continue
        if not ln.strip():
            flush_para(); flush_list(); i += 1; continue
        flush_list(); para.append(ln.strip()); i += 1
    flush_para(); flush_list()
    out.append("</div>")
    return "\n".join(out)

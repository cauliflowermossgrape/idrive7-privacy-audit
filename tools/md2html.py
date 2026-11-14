#!/usr/bin/env python3
"""Turn the report Markdown files into one printable HTML page.

Small converter for the subset these files use: headings, paragraphs,
nested lists, tables, fenced code, block quotes, rules, and inline
code/bold/italic/links.

usage: md2html.py OUT.html README.md findings/01.md ...
"""
import html
import re
import sys

def inline(text):
    parts = re.split(r'(`[^`]+`)', text)
    out = []
    for p in parts:
        if p.startswith('`') and p.endswith('`') and len(p) > 1:
            out.append('<code>' + html.escape(p[1:-1]) + '</code>')
            continue
        p = html.escape(p, quote=False)
        p = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: link(m), p)
        p = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', p)
        p = re.sub(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])', r'<em>\1</em>', p)
        out.append(p)
    return ''.join(out)


def link(m):
    label, href = m.group(1), m.group(2)
    if href.endswith('.md'):
        anchor = 'doc-' + re.sub(r'\W+', '-', href.split('/')[-1][:-3])
        return f'<a href="#{anchor}">{label}</a>'
    if not href.startswith(('http://', 'https://', '#')):
        return label  # a local file link would print as a path from the build machine
    return f'<a href="{href}">{label}</a>'


def split_row(line):
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|'):
        line = line[:-1]
    cells, cur, tick = [], '', False
    for ch in line:
        if ch == '`':
            tick = not tick
        if ch == '|' and not tick:
            cells.append(cur.strip())
            cur = ''
        else:
            cur += ch
    cells.append(cur.strip())
    return cells


LIST_RE = re.compile(r'^(\s*)([-*]|\d+\.)\s+(.*)$')


def convert(md, doc_id):
    lines = md.split('\n')
    out = [f'<section class="doc" id="{doc_id}">']
    i = 0
    para = []
    stack = []  # (indent, tag)

    def flush_para():
        if para:
            out.append('<p>' + inline(' '.join(para)) + '</p>')
            para.clear()

    def close_lists(to_indent=-1):
        while stack and stack[-1][0] > to_indent:
            out.append('</li></' + stack.pop()[1] + '>')

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith('```'):
            flush_para()
            j = i + 1
            code = []
            while j < len(lines) and not lines[j].strip().startswith('```'):
                code.append(lines[j])
                j += 1
            ind = len(line) - len(line.lstrip())
            code = [c[ind:] if c[:ind].strip() == '' else c for c in code]
            out.append('<pre>' + html.escape('\n'.join(code)) + '</pre>')
            i = j + 1
            continue
        m = LIST_RE.match(line)
        if m:
            flush_para()
            ind = len(m.group(1))
            tag = 'ol' if m.group(2)[0].isdigit() else 'ul'
            if stack and ind > stack[-1][0]:
                out.append(f'<{tag}><li>')
                stack.append((ind, tag))
            else:
                close_lists(ind)
                if stack and stack[-1][0] == ind:
                    out.append('</li><li>')
                else:
                    out.append(f'<{tag}><li>')
                    stack.append((ind, tag))
            out.append(inline(m.group(3)))
            i += 1
            continue
        if stack and s and (len(line) - len(line.lstrip())) > 0 and not s.startswith('|'):
            out.append(' ' + inline(s))
            i += 1
            continue
        if stack and s == '':
            # a blank line inside a list: keep the list open if more items follow
            j = i + 1
            while j < len(lines) and lines[j].strip() == '':
                j += 1
            if j < len(lines) and (LIST_RE.match(lines[j]) or lines[j].startswith(' ')):
                i = j
                continue
        close_lists()
        if s == '':
            flush_para()
        elif s.startswith('#'):
            flush_para()
            level = len(s) - len(s.lstrip('#'))
            text = s[level:].strip()
            out.append(f'<h{min(level + 1, 6)}>{inline(text)}</h{min(level + 1, 6)}>')
        elif s in ('---', '***'):
            flush_para()
            out.append('<hr>')
        elif s.startswith('|') and i + 1 < len(lines) and re.match(r'^\s*\|?\s*:?-{3,}', lines[i + 1]):
            flush_para()
            head = split_row(s)
            out.append('<table><thead><tr>' + ''.join(f'<th>{inline(c)}</th>' for c in head) + '</tr></thead><tbody>')
            i += 2
            while i < len(lines) and lines[i].strip().startswith('|'):
                out.append('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in split_row(lines[i])) + '</tr>')
                i += 1
            out.append('</tbody></table>')
            continue
        elif s.startswith('>'):
            flush_para()
            out.append('<blockquote>' + inline(s.lstrip('> ')) + '</blockquote>')
        else:
            para.append(s)
        i += 1
    flush_para()
    close_lists()
    out.append('</section>')
    return '\n'.join(out)


CSS = """
@page { size: A4; margin: 16mm 14mm 18mm 14mm; }
body { font-family: 'DejaVu Sans', 'Liberation Sans', Arial, sans-serif; font-size: 9.3pt; line-height: 1.42; color: #1a1d21; background: #fff; }
h1 { font-size: 20pt; margin: 0 0 6pt; color: #0b2a4a; }
h2 { font-size: 14pt; margin: 16pt 0 5pt; color: #0b2a4a; border-bottom: 1.5pt solid #0b4f8a; padding-bottom: 2pt; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; color: #0b4f8a; }
h4, h5 { font-size: 10pt; margin: 9pt 0 3pt; }
p { margin: 4pt 0; }
ul, ol { margin: 3pt 0 4pt; padding-left: 16pt; }
li { margin: 1.5pt 0; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 8pt; font-size: 8pt; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th { background: #e7eef6; text-align: left; }
th, td { border: 0.6pt solid #b8c4d0; padding: 2.5pt 4pt; vertical-align: top; overflow-wrap: anywhere; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 7.8pt; background: #f2f4f7; padding: 0 1.5pt; border-radius: 2pt; overflow-wrap: anywhere; }
pre { font-family: 'DejaVu Sans Mono', monospace; font-size: 7.2pt; background: #f2f4f7; border-left: 2pt solid #9fb3c8; padding: 4pt 6pt; white-space: pre-wrap; overflow-wrap: anywhere; page-break-inside: avoid; }
blockquote { margin: 5pt 0; padding: 3pt 8pt; border-left: 2pt solid #9fb3c8; color: #3a4450; }
hr { border: 0; border-top: 0.6pt solid #c8d2dc; margin: 10pt 0; }
a { color: #0b4f8a; text-decoration: none; }
.doc + .doc { page-break-before: always; }
.cover { page-break-after: always; padding-top: 70mm; }
.cover h1 { font-size: 28pt; }
.cover .sub { font-size: 13pt; color: #3a4450; margin-bottom: 18pt; }
.cover .meta { font-size: 9.5pt; color: #3a4450; line-height: 1.7; }
.cover .note { margin-top: 40mm; font-size: 8.5pt; color: #5a6470; border-top: 0.6pt solid #c8d2dc; padding-top: 6pt; }
.appx { font-size: 8.5pt; color: #5a6470; text-transform: uppercase; letter-spacing: 0.8pt; margin-bottom: 2pt; }
"""

COVER = """<div class="cover">
<h1>BMW MGU privacy audit</h1>
<div class="sub">What the stock iDrive 7 head unit collects, sends, stores, and how voice control works</div>
<div class="meta">Firmware BMW MGU P18_23w44.2 · OAP MainApp 8.3.2<br>Static analysis of the stock eMMC image and the BMW apps from the car<br>14 November 2026</div>
<div class="note">Code and configuration were read, not run, and no traffic was captured, so "can send" does not mean "did send". No personal values (VIN, coordinates, names, keys) are reproduced in this report.</div>
</div>"""


def main():
    out_path, files = sys.argv[1], sys.argv[2:]
    body = [COVER]
    for n, path in enumerate(files):
        with open(path, encoding='utf-8') as f:
            md = f.read()
        doc_id = 'doc-' + re.sub(r'\W+', '-', path.split('/')[-1][:-3])
        sec = convert(md, doc_id)
        if n > 0:
            sec = sec.replace('>', f'><div class="appx">Appendix {chr(64 + n)}</div>', 1)
        body.append(sec)
    page = ('<!doctype html><html><head><meta charset="utf-8"><title>BMW MGU privacy audit</title>'
            f'<style>{CSS}</style></head><body>' + '\n'.join(body) + '</body></html>')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(page)


if __name__ == '__main__':
    main()

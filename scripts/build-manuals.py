#!/usr/bin/env python3
"""Build the versioned Dutch PDF manuals from their Markdown sources."""
from html import escape
from pathlib import Path
import re
import textwrap

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
FONTS = Path('/usr/share/fonts/truetype/dejavu')
for name, file in [('DejaVu', 'DejaVuSans.ttf'), ('DejaVuBold', 'DejaVuSans-Bold.ttf'),
                   ('DejaVuMono', 'DejaVuSansMono.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(FONTS / file)))
pdfmetrics.registerFontFamily('DejaVu', normal='DejaVu', bold='DejaVuBold', italic='DejaVu', boldItalic='DejaVuBold')
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyNL', fontName='DejaVu', fontSize=9.4, leading=14, spaceAfter=7))
styles.add(ParagraphStyle(name='TitleNL', fontName='DejaVuBold', fontSize=23, leading=29, textColor=colors.HexColor('#17364d'), spaceAfter=18))
styles.add(ParagraphStyle(name='SectionNL', fontName='DejaVuBold', fontSize=14, leading=19, textColor=colors.HexColor('#17364d'), spaceBefore=15, spaceAfter=9, keepWithNext=True))
styles.add(ParagraphStyle(name='SubNL', parent=styles['SectionNL'], fontSize=11, leading=15))
styles.add(ParagraphStyle(name='BulletNL', parent=styles['BodyNL'], leftIndent=12, firstLineIndent=-9))
styles.add(ParagraphStyle(name='CodeNL', fontName='DejaVuMono', fontSize=7.4, leading=10.4, leftIndent=8, borderPadding=7, backColor=colors.HexColor('#f0f3f5'), spaceBefore=4, spaceAfter=10))


def inline(text):
    text = escape(text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<link href="\2" color="#1b5c88">\1</link>', text)
    text = re.sub(r'`([^`]+)`', r'<font name="DejaVuMono">\1</font>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    return text


def flowables(text):
    out, para, code = [], [], None
    def flush():
        if para:
            out.append(Paragraph(inline(' '.join(para)), styles['BodyNL']))
            para.clear()
    for line in text.splitlines():
        if line.startswith('```'):
            flush()
            if code is None:
                code = []
            else:
                wrapped = []
                for value in code:
                    wrapped.extend(textwrap.wrap(value, width=99, replace_whitespace=False,
                                                  drop_whitespace=False, subsequent_indent='    ') or [''])
                out.append(Preformatted('\n'.join(wrapped), styles['CodeNL']))
                code = None
            continue
        if code is not None:
            code.append(line)
            continue
        if not line.strip():
            flush()
        elif line.startswith('#'):
            flush()
            level = len(line) - len(line.lstrip('#'))
            out.append(Paragraph(inline(line.lstrip('#').strip()), styles['TitleNL' if level == 1 else 'SectionNL' if level == 2 else 'SubNL']))
        elif line.startswith('- ') or re.match(r'^\d+\. ', line):
            flush()
            value = '• ' + line[2:] if line.startswith('- ') else line
            out.append(Paragraph(inline(value), styles['BulletNL']))
        else:
            para.append(line)
    flush()
    return out


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#bdcbd6'))
    canvas.line(18*mm, 16*mm, 192*mm, 16*mm)
    canvas.setFont('DejaVu', 7)
    canvas.setFillColor(colors.HexColor('#42576a'))
    canvas.drawString(18*mm, 11*mm, 'PI3TWE · SvxLink-Dash-V3.1 · 21 oktober 2026')
    canvas.drawRightString(192*mm, 11*mm, str(doc.page))
    canvas.restoreState()


def main():
    output = ROOT / 'docs/pdf'
    output.mkdir(exist_ok=True)
    for stem in ['BOUW-EN-BEHEER-NL', 'GEBRUIKERSKAART-NL', 'HERBOUWCONTROLE-NL']:
        source = ROOT / 'docs' / (stem + '.md')
        target = output / (stem + '.pdf')
        doc = SimpleDocTemplate(str(target), pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
                                topMargin=18*mm, bottomMargin=23*mm,
                                title=source.read_text().splitlines()[0].lstrip('# '),
                                author='PI3TWE / videobuff')
        doc.build(flowables(source.read_text()), onFirstPage=footer, onLaterPages=footer)
        print(target.relative_to(ROOT))


if __name__ == '__main__':
    main()

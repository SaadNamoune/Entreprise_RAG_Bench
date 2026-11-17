"""Attachment files built from content specs, reproducibly (same input, same bytes).

One builder per modality of the stratification (design document, decision B-6): born-digital
PDF, DOCX, XLSX, chart image, scanned document (image-only PDF, degraded on purpose) and a
decorative logo. Office files carry fixed timestamps and PDFs are written in reportlab's
invariant mode, so the file hashes in the corpus never change between builds.
"""

from __future__ import annotations

import io
import random
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_FIXED_ZIP_TIME = (2027, 1, 1, 0, 0, 0)
_FIXED_W3CDTF = "2027-01-01T00:00:00Z"


@dataclass
class Block:
    kind: str  # "title", "heading", "paragraph", "table"
    text: str = ""
    rows: list[list[str]] | None = None


def _font_path() -> str:
    from matplotlib import font_manager

    return font_manager.findfont("DejaVu Sans")


def normalize_office_zip(path: Path) -> None:
    """Rewrite a DOCX/XLSX/PPTX zip with fixed entry times and fixed document dates."""
    with zipfile.ZipFile(path) as zin:
        entries = [(i, zin.read(i.filename)) for i in zin.infolist()]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for info, data in entries:
            if info.filename == "docProps/core.xml":
                text = data.decode("utf-8")
                text = re.sub(r"(<dcterms:(created|modified)[^>]*>)[^<]*(</dcterms:\2>)",
                              rf"\g<1>{_FIXED_W3CDTF}\g<3>", text)
                data = text.encode("utf-8")
            fixed = zipfile.ZipInfo(info.filename, date_time=_FIXED_ZIP_TIME)
            fixed.compress_type = zipfile.ZIP_DEFLATED
            fixed.external_attr = info.external_attr
            zout.writestr(fixed, data)


def build_pdf(path: Path, blocks: list[Block], header: str = "") -> int:
    """A born-digital PDF with a text layer. Returns the number of pages."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    width, height = A4
    y = height - 60
    pages = 1

    def line(text: str, size: int = 10, bold: bool = False, x: float = 60) -> None:
        nonlocal y, pages
        if y < 70:
            c.showPage()
            pages += 1
            y = height - 60
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x, y, text)
        y -= size + 6

    if header:
        line(header, 9)
        y -= 6
    for b in blocks:
        if b.kind == "title":
            line(b.text, 16, True)
            y -= 4
        elif b.kind == "heading":
            line(b.text, 12, True)
        elif b.kind == "paragraph":
            for chunk in _wrap(b.text, 95):
                line(chunk)
            y -= 4
        elif b.kind == "table":
            for row in b.rows or []:
                c.setFont("Helvetica", 10)
                x = 60
                for i, cell in enumerate(row):
                    c.drawString(x, y, cell)
                    x += 170 if i == 0 else 150
                y -= 16
            y -= 6
    c.showPage()
    c.save()
    return pages


def build_docx(path: Path, blocks: list[Block], when: datetime, author: str) -> None:
    from docx import Document

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    for b in blocks:
        if b.kind == "title":
            doc.add_heading(b.text, level=0)
        elif b.kind == "heading":
            doc.add_heading(b.text, level=1)
        elif b.kind == "paragraph":
            doc.add_paragraph(b.text)
        elif b.kind == "table" and b.rows:
            table = doc.add_table(rows=len(b.rows), cols=len(b.rows[0]))
            for r, row in enumerate(b.rows):
                for col, cell in enumerate(row):
                    table.cell(r, col).text = cell
    props = doc.core_properties
    props.author = author
    props.last_modified_by = author
    props.created = when.replace(tzinfo=None)
    props.modified = when.replace(tzinfo=None)
    props.revision = 1
    doc.save(str(path))
    normalize_office_zip(path)


def build_xlsx(path: Path, sheet: str, rows: list[list[str]], author: str) -> None:
    from openpyxl import Workbook

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for row in rows:
        ws.append(row)  # values stay strings: the anchor is the text a reader sees
    for col, w in zip("ABCD", (28, 12, 16, 16)):
        ws.column_dimensions[col].width = w
    wb.properties.creator = author
    wb.save(str(path))
    normalize_office_zip(path)


def build_chart_png(path: Path, title: str, x: list[float], y: list[float], xlabel: str, ylabel: str,
                    marker: tuple[float, float], marker_label: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.4, 4.0), dpi=100)
    ax.plot(x, y, linewidth=2)
    ax.plot([marker[0]], [marker[1]], "o")
    ax.annotate(marker_label, marker, xytext=(10, 12), textcoords="offset points")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, format="png", metadata={"Software": None})
    plt.close(fig)


def build_logo_png(path: Path, text: str, color: tuple[int, int, int] = (20, 70, 140)) -> None:
    from PIL import Image, ImageDraw, ImageFont

    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (240, 60), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle((4, 4, 54, 56), fill=color)
    draw.text((66, 16), text, fill=color, font=ImageFont.truetype(_font_path(), 22))
    img.save(path, format="PNG", optimize=False)


def build_scan_pdf(path: Path, lines: list[str], dpi: int = 150, noise: float = 0.05,
                   skew_degrees: float = 1.0, jpeg_quality: int = 70, seed: int = 0) -> int:
    """An image-only PDF: the page is rendered as pixels, degraded, and has no text layer.

    This is the case a text pipeline cannot read without OCR, which the platform reports as
    "no extractable text" today (design document, section 2).
    """
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = int(8.27 * dpi), int(11.69 * dpi)
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(_font_path(), int(dpi * 0.16))
    y = int(dpi * 0.9)
    for text in lines:
        draw.text((int(dpi * 0.9), y), text, fill=20, font=font)
        y += int(dpi * 0.32)
    rng = random.Random(seed)
    px = img.load()
    for _ in range(int(w * h * noise * 0.02)):
        px[rng.randrange(w), rng.randrange(h)] = rng.randrange(0, 160)
    img = img.rotate(skew_degrees, fillcolor=255, resample=Image.Resampling.BICUBIC)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=jpeg_quality)
    buf.seek(0)
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    c.drawImage(ImageReader(buf), 0, 0, width=A4[0], height=A4[1])
    c.showPage()
    c.save()
    return 1


def _wrap(text: str, width: int) -> list[str]:
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width and line:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out

"""Book-style PDF generation for stories."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

# Page geometry (mm)
PAGE_W = 210
PAGE_H = 297
MARGIN_TOP = 30
MARGIN_BOTTOM = 25
MARGIN_OUTER = 25
MARGIN_INNER = 30
BODY_W = PAGE_W - MARGIN_OUTER - MARGIN_INNER

# DejaVu Serif TTF paths (installed via fonts-dejavu-core)
_FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
_FONTS = {
    "": _FONT_DIR / "DejaVuSerif.ttf",
    "B": _FONT_DIR / "DejaVuSerif-Bold.ttf",
    "I": _FONT_DIR / "DejaVuSerif.ttf",         # italic not shipped, use regular
    "BI": _FONT_DIR / "DejaVuSerif-Bold.ttf",    # bold-italic not shipped, use bold
}
FONT = "DejaVuSerif"


class BookPDF(FPDF):
    """Custom PDF with book-style headers and footers."""

    def __init__(self, title: str = "AI Publishing House"):
        super().__init__()
        self.book_title = title
        self._chapter_title = ""
        self.set_auto_page_break(auto=True, margin=MARGIN_BOTTOM)
        self.set_top_margin(MARGIN_TOP)
        # Register Unicode font
        for style, path in _FONTS.items():
            self.add_font(FONT, style=style, fname=str(path))

    def header(self):
        if self.page_no() <= 1:
            return
        self.set_font(FONT, "I", 8)
        self.set_text_color(140, 140, 140)
        self.set_y(15)
        if self.page_no() % 2 == 0:
            self.set_x(MARGIN_OUTER)
            self.cell(BODY_W, 5, self.book_title, align="L")
        else:
            self.set_x(MARGIN_INNER)
            self.cell(BODY_W, 5, self._chapter_title, align="R")
        # Thin rule under header
        self.set_draw_color(200, 200, 200)
        y = self.get_y() + 6
        self.line(MARGIN_OUTER, y, PAGE_W - MARGIN_OUTER, y)
        # Force body content below the header
        self.set_y(MARGIN_TOP)

    def footer(self):
        if self.page_no() <= 1:
            return
        self.set_y(-20)
        self.set_font(FONT, "", 9)
        self.set_text_color(140, 140, 140)
        self.cell(0, 10, str(self.page_no()), align="C")

    def _title_page(self, title: str, subtitle: str = "", year: str = ""):
        self.add_page()
        self.set_y(90)
        # Decorative rule
        self.set_draw_color(108, 92, 231)
        self.set_line_width(0.5)
        cx = PAGE_W / 2
        self.line(cx - 30, self.get_y(), cx + 30, self.get_y())

        self.ln(10)
        self.set_font(FONT, "B", 28)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 12, title, align="C")

        if subtitle:
            self.ln(4)
            self.set_font(FONT, "I", 14)
            self.set_text_color(100, 100, 100)
            self.multi_cell(0, 8, subtitle, align="C")

        self.ln(8)
        self.set_draw_color(108, 92, 231)
        self.line(cx - 30, self.get_y(), cx + 30, self.get_y())

        self.ln(12)
        self.set_font(FONT, "", 11)
        self.set_text_color(120, 120, 120)
        self.multi_cell(0, 7, "AI Publishing House", align="C")

        if year:
            self.ln(2)
            self.set_font(FONT, "", 10)
            self.multi_cell(0, 7, year, align="C")

    def _chapter_start(self, title: str, genre: str = ""):
        """Start a new chapter with a styled title."""
        self._chapter_title = title
        self.add_page()
        self.set_y(60)

        # Genre label above title
        if genre:
            self.set_font(FONT, "", 9)
            self.set_text_color(108, 92, 231)
            self.cell(0, 6, genre.upper().replace("_", " "), align="C", new_x="LMARGIN", new_y="NEXT")
            self.ln(4)

        self.set_font(FONT, "B", 22)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 10, title, align="C")

        # Decorative separator
        self.ln(6)
        cx = PAGE_W / 2
        self.set_draw_color(108, 92, 231)
        self.set_line_width(0.3)
        self.line(cx - 20, self.get_y(), cx + 20, self.get_y())
        self.ln(10)

    def _body_text(self, text: str):
        """Render story body text with book typography."""
        self.set_font(FONT, "", 11)
        self.set_text_color(40, 40, 40)
        self.set_left_margin(MARGIN_INNER)
        self.set_right_margin(MARGIN_OUTER)

        paragraphs = text.split("\n")
        first = True
        for para in paragraphs:
            para = para.strip()
            if not para:
                if not first:
                    self.ln(3)
                continue
            # First paragraph: no indent. Subsequent: indent.
            if first:
                first = False
            else:
                self.set_x(MARGIN_INNER + 8)
            self.multi_cell(BODY_W, 6, para, align="J")
            self.ln(1)

        # Reset margins
        self.set_left_margin(10)
        self.set_right_margin(10)


def generate_single_story_pdf(story) -> bytes:
    """Generate a book-style PDF for a single story."""
    pdf = BookPDF(title=story.title or "Untitled")
    year = story.created_at.strftime("%Y") if story.created_at else ""
    genre = story.prompt.genre if story.prompt else ""

    pdf._title_page(
        title=story.title or "Untitled",
        subtitle=genre.replace("_", " ").title() if genre else "",
        year=year,
    )

    pdf._chapter_start(story.title or "Untitled", genre=genre)
    pdf._body_text(story.current_draft or "")

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def generate_anthology_pdf(stories: list) -> bytes:
    """Generate a book-style PDF containing multiple stories."""
    now = datetime.now(timezone.utc)

    pdf = BookPDF(title="AI Publishing House Anthology")

    pdf._title_page(
        title="Collected Stories",
        subtitle="AI Publishing House",
        year=now.strftime("%Y"),
    )

    # Table of contents
    pdf.add_page()
    pdf._chapter_title = "Contents"
    pdf.set_y(50)
    pdf.set_font(FONT, "B", 18)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 10, "Contents", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(12)

    pdf.set_font(FONT, "", 11)
    pdf.set_text_color(60, 60, 60)
    for i, story in enumerate(stories, 1):
        title = story.title or "Untitled"
        genre = story.prompt.genre.replace("_", " ").title() if story.prompt and story.prompt.genre else ""
        label = f"{i}.  {title}"
        if genre:
            label += f"   ({genre})"
        pdf.set_x(MARGIN_INNER)
        pdf.cell(BODY_W, 8, label, new_x="LMARGIN", new_y="NEXT")

    # Stories
    for story in stories:
        genre = story.prompt.genre if story.prompt else ""
        pdf._chapter_start(story.title or "Untitled", genre=genre)
        pdf._body_text(story.current_draft or "")

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()

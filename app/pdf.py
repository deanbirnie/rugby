"""A4 match poster: a print-ready PDF with the match details and a big QR
code linking to the prediction page. Drawn with reportlab (pure Python, no
system dependencies) in the Springbok green/gold theme.
"""
import io

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.models import Match
from app.qr import generate_qr_png

BOK_GREEN = HexColor("#00543C")
BOK_GREEN_DARK = HexColor("#00301F")
BOK_GOLD = HexColor("#FFB81C")
BOK_INK = HexColor("#1A1A1A")
BOK_GREY = HexColor("#6b6b6b")

PAGE_W, PAGE_H = A4  # 595 x 842 pt


def _fitted_font_size(c, text: str, font: str, max_size: float, max_width: float) -> float:
    """Largest font size (capped at max_size) at which text fits max_width."""
    size = max_size
    while size > 8 and c.stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def _centred(c, text: str, y: float, font: str, size: float, color) -> None:
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawCentredString(PAGE_W / 2, y, text)


def build_match_poster(match: Match, predict_url: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Bokke Predictions - Springboks vs {match.opponent}")

    margin = 40

    # Header band
    band_h = 110
    c.setFillColor(BOK_GREEN)
    c.rect(0, PAGE_H - band_h, PAGE_W, band_h, stroke=0, fill=1)
    c.setFillColor(BOK_GOLD)
    c.rect(0, PAGE_H - band_h - 6, PAGE_W, 6, stroke=0, fill=1)

    c.setFont("Helvetica-Bold", 30)
    c.setFillColor(white)
    brand = "BOKKE "
    brand2 = "PREDICTIONS"
    total_w = c.stringWidth(brand + brand2, "Helvetica-Bold", 30)
    x = (PAGE_W - total_w) / 2
    c.drawString(x, PAGE_H - 62, brand)
    c.setFillColor(BOK_GOLD)
    c.drawString(x + c.stringWidth(brand, "Helvetica-Bold", 30), PAGE_H - 62, brand2)
    _centred(c, "Winner takes the pot!", PAGE_H - 88, "Helvetica", 13, white)

    # Headline: Springboks vs Opponent (shrink to fit long names)
    y = PAGE_H - band_h - 70
    headline = f"SPRINGBOKS  vs  {match.opponent.upper()}"
    size = _fitted_font_size(c, headline, "Helvetica-Bold", 34, PAGE_W - 2 * margin)
    _centred(c, headline, y, "Helvetica-Bold", size, BOK_INK)

    # Match details line(s)
    y -= 30
    when = match.kickoff_at.strftime("%A %d %B %Y  ·  %H:%M")
    _centred(c, when, y, "Helvetica", 15, BOK_GREY)
    details = "  ·  ".join(filter(None, [match.competition, match.venue]))
    if details:
        y -= 22
        size = _fitted_font_size(c, details, "Helvetica", 15, PAGE_W - 2 * margin)
        _centred(c, details, y, "Helvetica", size, BOK_GREY)

    # QR block: gold-bordered white card with the code inside
    qr_size = 300
    card_pad = 18
    card_size = qr_size + 2 * card_pad
    card_x = (PAGE_W - card_size) / 2
    card_y = y - 60 - card_size

    c.setFillColor(white)
    c.setStrokeColor(BOK_GOLD)
    c.setLineWidth(5)
    c.roundRect(card_x, card_y, card_size, card_size, 14, stroke=1, fill=1)

    qr_png = generate_qr_png(predict_url, box_size=16)
    c.drawImage(
        ImageReader(io.BytesIO(qr_png)),
        card_x + card_pad,
        card_y + card_pad,
        qr_size,
        qr_size,
    )

    # Call to action under the QR
    y = card_y - 42
    _centred(c, "SCAN TO LEAVE YOUR PREDICTION", y, "Helvetica-Bold", 20, BOK_GREEN)

    if float(match.buy_in_amount or 0) > 0:
        y -= 30
        _centred(
            c,
            f"Buy-in: R{float(match.buy_in_amount):.2f} per prediction",
            y,
            "Helvetica-Bold",
            15,
            BOK_INK,
        )

    y -= 28
    _centred(
        c,
        "Nail the exact score and the whole pot is yours.",
        y,
        "Helvetica",
        13,
        BOK_GREY,
    )
    y -= 18
    _centred(
        c,
        "Nobody gets it? The pot rolls over to the next match.",
        y,
        "Helvetica",
        13,
        BOK_GREY,
    )

    # Footer band with the fallback URL
    c.setFillColor(BOK_GREEN_DARK)
    c.rect(0, 0, PAGE_W, 46, stroke=0, fill=1)
    _centred(c, f"No camera? Type this link:  {predict_url}", 18, "Helvetica", 12, white)

    c.showPage()
    c.save()
    return buf.getvalue()

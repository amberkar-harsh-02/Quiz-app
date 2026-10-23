"""PDFs: a student's review of one game, the professor's class report for a game, and a quiz's answer key."""
from io import BytesIO
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

FONT_DIR = Path(__file__).parent / "fonts"

LETTERS = {"red": "A", "blue": "B", "yellow": "C", "green": "D"}
# Same tile colors as the app (frontend/src/answers.js)
ANSWER_COLORS = {"red": (57, 73, 171), "blue": (0, 121, 107), "yellow": (184, 82, 10), "green": (173, 20, 87)}
INK = (23, 32, 51)
MUTED = (90, 103, 121)
LINE = (213, 220, 229)
OK = (30, 122, 62)
BAD = (180, 35, 24)
SOFT = (243, 245, 248)

MAX_IMAGE_W = 120  # mm
MAX_IMAGE_H = 70   # mm


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


class QuizPDF(FPDF):
    def __init__(self, title: str):
        super().__init__(format="letter")
        self.doc_title = title
        # Built-in PDF fonts only cover Latin-1; this TTF handles dashes, curly quotes and accents
        self.add_font("Atkinson", "", str(FONT_DIR / "AtkinsonHyperlegible-Regular.ttf"))
        self.add_font("Atkinson", "B", str(FONT_DIR / "AtkinsonHyperlegible-Bold.ttf"))
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(True, margin=18)
        self.set_title(title)
        self.set_creator("Quiz App")
        self.add_page()

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Atkinson", "", 9)
        self.set_text_color(*MUTED)
        self.cell(0, 6, self.doc_title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def footer(self):
        self.set_y(-12)
        self.set_font("Atkinson", "", 9)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"Page {self.page_no()} of {{nb}}", align="C")

    # --- building blocks ---

    def text_block(self, text, size=11, bold=False, color=INK, height=None, gap=0):
        self.set_font("Atkinson", "B" if bold else "", size)
        self.set_text_color(*color)
        self.multi_cell(0, height or size * 0.5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if gap:
            self.ln(gap)

    def title_block(self, title, lines):
        self.text_block(title, size=20, bold=True, height=9, gap=1)
        for line in lines:
            self.text_block(line, size=11, color=MUTED, height=6)
        self.ln(4)
        self.rule()

    def rule(self):
        self.set_draw_color(*LINE)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)

    def stats(self, items):
        """A row of label/value pairs, e.g. [("Score", "2914"), ("Place", "2nd of 5")]."""
        width = (self.w - self.l_margin - self.r_margin) / len(items)
        y = self.get_y()
        for i, (label, value) in enumerate(items):
            self.set_xy(self.l_margin + i * width, y)
            self.set_font("Atkinson", "", 9)
            self.set_text_color(*MUTED)
            self.cell(width, 5, label)
            self.set_xy(self.l_margin + i * width, y + 5)
            self.set_font("Atkinson", "B", 16)
            self.set_text_color(*INK)
            self.cell(width, 8, value)
        self.set_xy(self.l_margin, y + 16)
        self.rule()

    def answer_line(self, label, color_key, text, label_color=MUTED, label_width=32, bold=False, text_color=INK):
        """'Your answer:' [B] Preimage resistance, with the letter in its answer color."""
        self.set_font("Atkinson", "", 10)
        self.set_text_color(*label_color)
        self.cell(label_width, 7, label)
        if color_key in LETTERS:
            x, y = self.get_x(), self.get_y()
            self.set_fill_color(*ANSWER_COLORS[color_key])
            self.rect(x, y + 0.8, 5.4, 5.4, style="F")
            self.set_font("Atkinson", "B", 9)
            self.set_text_color(255, 255, 255)
            self.set_xy(x, y)
            self.cell(5.4, 7, LETTERS[color_key], align="C")
            self.set_x(x + 7.5)
        self.set_font("Atkinson", "B" if bold else "", 11)
        self.set_text_color(*text_color)
        self.multi_cell(0, 7, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def image_block(self, data: bytes, width_px: int, height_px: int):
        if not data or not width_px or not height_px:
            return
        scale = min(MAX_IMAGE_W / width_px, MAX_IMAGE_H / height_px)
        w, h = width_px * scale, height_px * scale
        if self.get_y() + h > self.h - self.b_margin:
            self.add_page()
        self.image(BytesIO(data), x=self.l_margin, y=self.get_y(), w=w, h=h)
        self.ln(h + 3)

    def explanation_block(self, text):
        self.ln(1)
        self.set_fill_color(*SOFT)
        self.set_font("Atkinson", "", 10)
        self.set_text_color(*INK)
        self.multi_cell(0, 5.5, f"Why: {text}", fill=True, padding=2.5, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def keep_together(self, height):
        """Starts a new page if fewer than `height` mm are left, so a question isn't split oddly."""
        if self.get_y() + height > self.h - self.b_margin:
            self.add_page()


def review_pdf(*, quiz_title, played_on, student_name, score, rank, total_players, correct, questions) -> bytes:
    """questions: dicts with number, text, image (bytes, w, h) or None, selected, selected_text,
    correct_option, correct_text, explanation."""
    pdf = QuizPDF(f"{quiz_title}: review for {student_name}")
    pdf.title_block(quiz_title, [f"Review for {student_name}", f"Played {played_on}"])
    pdf.stats([
        ("Score", str(score)),
        ("Place", f"{ordinal(rank)} of {total_players}"),
        ("Correct", f"{correct} of {len(questions)}"),
    ])

    for q in questions:
        pdf.keep_together(40)
        pdf.text_block(f"{q['number']}. {q['text']}", size=13, bold=True, height=6.5, gap=2)
        if q.get("image"):
            pdf.image_block(*q["image"])
        if q["selected"] is None:
            pdf.answer_line("Your answer:", None, "No answer")
            verdict, verdict_color = "Not answered", MUTED
        else:
            pdf.answer_line("Your answer:", q["selected"], q["selected_text"])
            is_correct = q["selected"] == q["correct_option"]
            verdict, verdict_color = ("Correct", OK) if is_correct else ("Incorrect", BAD)
        if q["selected"] != q["correct_option"]:
            pdf.answer_line("Correct answer:", q["correct_option"], q["correct_text"])
        pdf.text_block(verdict, size=10, bold=True, color=verdict_color, height=6)
        if q.get("explanation"):
            pdf.explanation_block(q["explanation"])
        pdf.ln(4)
        pdf.rule()
    return bytes(pdf.output())


def class_report_pdf(*, analytics, questions, room_code, played_on) -> bytes:
    """analytics: the /analytics JSON. questions: dicts with text, correct_option, correct_text,
    in the same order as analytics['questions']."""
    overview = analytics["overview"]
    pdf = QuizPDF(f"{analytics['quiz_title']}: class report")
    pdf.title_block(analytics["quiz_title"], [f"Class report, played {played_on}", f"Room {room_code}"])
    pdf.stats([
        ("Students", str(overview["total_students"])),
        ("Average score", str(overview["average_score"])),
        ("Class accuracy", f"{overview['average_accuracy']}%"),
    ])

    pdf.text_block("Questions", size=14, bold=True, height=7, gap=2)
    for i, (stats, q) in enumerate(zip(analytics["questions"], questions), start=1):
        pdf.keep_together(42)
        pdf.text_block(f"{i}. {q['text']}", size=12, bold=True, height=6, gap=1)
        tone = OK if stats["accuracy"] >= 70 else (MUTED if stats["accuracy"] >= 40 else BAD)
        pdf.text_block(f"{stats['accuracy']}% correct ({stats['correct_count']} of {stats['correct_count'] + stats['incorrect_count']} answers)",
                       size=10, bold=True, color=tone, height=6)
        pdf.answer_line("Correct answer:", q["correct_option"], q["correct_text"])
        answered = sum(stats["spread"].values())
        counts = "    ".join(
            f"{LETTERS[c]}: {stats['spread'][c]} ({round(stats['spread'][c] / answered * 100) if answered else 0}%)"
            for c in LETTERS
        )
        pdf.text_block(f"Answers  {counts}", size=10, color=MUTED, height=6, gap=3)

    pdf.add_page()
    pdf.text_block("Students", size=14, bold=True, height=7, gap=2)
    widths = (90, 30, 30, 30)
    headers = ("Name", "Score", "Correct", "Accuracy")
    pdf.set_font("Atkinson", "B", 10)
    pdf.set_text_color(*MUTED)
    pdf.set_fill_color(*SOFT)
    for w, h in zip(widths, headers):
        pdf.cell(w, 8, h, fill=True, align="L" if h == "Name" else "R")
    pdf.ln(8)
    pdf.set_font("Atkinson", "", 10)
    pdf.set_text_color(*INK)
    total = len(questions)
    for s in analytics["students"]:
        row = (s["name"], str(s["final_score"]), f"{s['total_correct']} of {total}", f"{s['accuracy']}%")
        for w, value, header in zip(widths, row, headers):
            pdf.cell(w, 7, value, align="L" if header == "Name" else "R")
        pdf.ln(7)
        pdf.set_draw_color(*LINE)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + sum(widths), pdf.get_y())
    return bytes(pdf.output())


def solutions_pdf(*, quiz_title, subtitle, questions) -> bytes:
    """questions: dicts with number, text, image (bytes, w, h) or None, options ({color: text}),
    correct_option, explanation."""
    pdf = QuizPDF(f"{quiz_title}: answer key")
    pdf.title_block(quiz_title, [subtitle, f"{len(questions)} {'question' if len(questions) == 1 else 'questions'}"])

    for q in questions:
        pdf.keep_together(48)
        pdf.text_block(f"{q['number']}. {q['text']}", size=13, bold=True, height=6.5, gap=2)
        if q.get("image"):
            pdf.image_block(*q["image"])
        for color in LETTERS:
            if not q["options"].get(color):
                continue
            if color == q["correct_option"]:
                pdf.answer_line("", color, f"{q['options'][color]}  (correct answer)", label_width=4, bold=True, text_color=OK)
            else:
                pdf.answer_line("", color, q["options"][color], label_width=4)
        if q.get("explanation"):
            pdf.explanation_block(q["explanation"])
        pdf.ln(4)
        pdf.rule()
    return bytes(pdf.output())

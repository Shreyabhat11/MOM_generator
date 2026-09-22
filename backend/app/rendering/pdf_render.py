"""Renders a validated MeetingMinutes directly to a professionally
formatted PDF using reportlab/platypus (spec section 19). We generate the
PDF independently from the DOCX (rather than converting DOCX->PDF via
LibreOffice) to avoid a heavy external binary dependency in the Docker
image - see README "Known limitations" for the trade-off this implies
(the two documents share content and structure but are laid out by two
separate renderers, so minor formatting differences are possible)."""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.schemas import MeetingMinutes

_ACCENT = colors.HexColor("#1F3A5F")


def _styles():
    base = getSampleStyleSheet()
    base.add(ParagraphStyle(name="MomTitle", fontSize=20, leading=24, spaceAfter=14, textColor=_ACCENT, alignment=1))
    base.add(ParagraphStyle(name="MomHeading", fontSize=13, leading=16, spaceBefore=14, spaceAfter=6, textColor=_ACCENT))
    base.add(ParagraphStyle(name="MomBody", fontSize=10.5, leading=15))
    return base


def _bullet_list(items: list[str], styles) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(i, styles["MomBody"])) for i in items],
        bulletType="bullet",
        leftIndent=16,
    )


def render_pdf(minutes: MeetingMinutes) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        title=minutes.meeting_title or "Minutes of Meeting",
    )
    styles = _styles()
    story = []

    story.append(Paragraph(minutes.meeting_title or "Minutes of Meeting", styles["MomTitle"]))
    meta_rows = [
        ["Date", minutes.date or "Not mentioned"],
        ["Time", minutes.time or "Not mentioned"],
        ["Location", minutes.location or "Not mentioned"],
        ["Organizer", minutes.organizer or "Not mentioned"],
    ]
    meta_table = Table(meta_rows, colWidths=[1.3 * inch, 4.7 * inch])
    meta_table.setStyle(
        TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(meta_table)

    def section(title: str, body):
        story.append(Paragraph(title, styles["MomHeading"]))
        story.append(body)
        story.append(Spacer(1, 4))

    section("Attendees", _bullet_list(minutes.attendees, styles) if minutes.attendees else Paragraph("Not mentioned", styles["MomBody"]))
    section("Agenda", _bullet_list(minutes.agenda, styles) if minutes.agenda else Paragraph("Not mentioned", styles["MomBody"]))

    narrative = minutes.field_confidence.get("discussion_narrative")
    if narrative:
        discussion_body = Paragraph(narrative, styles["MomBody"])
    elif minutes.discussion_points:
        discussion_body = _bullet_list(minutes.discussion_points, styles)
    else:
        discussion_body = Paragraph("Not mentioned", styles["MomBody"])
    section("Discussion Summary", discussion_body)

    section("Decisions", _bullet_list(minutes.decisions, styles) if minutes.decisions else Paragraph("Not mentioned", styles["MomBody"]))

    story.append(Paragraph("Action Items", styles["MomHeading"]))
    if minutes.action_items:
        rows = [["Action", "Owner", "Deadline"]] + [
            [i.task, i.owner or "Not mentioned", i.deadline or "Not mentioned"] for i in minutes.action_items
        ]
        table = Table(rows, colWidths=[3.2 * inch, 1.4 * inch, 1.4 * inch])
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), _ACCENT),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F9")]),
            ])
        )
        story.append(table)
    else:
        story.append(Paragraph("Not mentioned", styles["MomBody"]))
    story.append(Spacer(1, 4))

    section("Risks", _bullet_list(minutes.risks, styles) if minutes.risks else Paragraph("Not mentioned", styles["MomBody"]))
    section("Open Questions", _bullet_list(minutes.open_questions, styles) if minutes.open_questions else Paragraph("Not mentioned", styles["MomBody"]))
    section("Next Meeting", Paragraph(minutes.next_meeting or "Not mentioned", styles["MomBody"]))
    section("Summary", Paragraph(minutes.summary or "Not available", styles["MomBody"]))

    doc.build(story)
    return buf.getvalue()

from __future__ import annotations

import re
from html import escape
from io import BytesIO


def markdown_to_pdf_bytes(report_markdown: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        ListFlowable,
        ListItem,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = BytesIO()
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        alignment=TA_LEFT,
        spaceAfter=5,
    )
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=TA_LEFT,
        spaceAfter=10,
    )
    heading1_style = ParagraphStyle(
        "ReportHeading1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        alignment=TA_LEFT,
        spaceBefore=10,
        spaceAfter=6,
    )
    heading2_style = ParagraphStyle(
        "ReportHeading2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        alignment=TA_LEFT,
        spaceBefore=7,
        spaceAfter=4,
    )
    table_header_style = ParagraphStyle(
        "ReportTableHeader",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
    )
    table_cell_style = ParagraphStyle(
        "ReportTableCell",
        parent=body_style,
        fontSize=8.5,
        leading=11,
    )

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )
    story = []
    list_items = []
    list_type = "bullet"
    table_rows = []

    def flush_list() -> None:
        nonlocal list_items, list_type
        if list_items:
            story.append(
                ListFlowable(
                    [ListItem(Paragraph(item, body_style)) for item in list_items],
                    bulletType=list_type,
                    bulletFontName="Helvetica",
                    bulletFontSize=7 if list_type == "bullet" else 9,
                    leftIndent=16,
                    bulletIndent=4,
                    itemSpace=3,
                )
            )
            story.append(Spacer(1, 6))
            list_items = []
            list_type = "bullet"

    def flush_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        if len(table_rows) >= 2 and _is_markdown_table_separator(table_rows[1]):
            rows = [table_rows[0], *table_rows[2:]]
            data = []
            for row_index, row in enumerate(rows):
                style = table_header_style if row_index == 0 else table_cell_style
                data.append(
                    [
                        Paragraph(_markdown_to_reportlab_text(cell), style)
                        for cell in _split_table_row(row)
                    ]
                )
            if data:
                col_count = max(len(row) for row in data)
                for row in data:
                    row.extend(
                        Paragraph("", table_cell_style)
                        for _ in range(col_count - len(row))
                    )
                table = Table(data, repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
                            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 5),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 8))
        else:
            for row in table_rows:
                story.append(Paragraph(_markdown_to_reportlab_text(row), body_style))
        table_rows = []

    def append_list_item(item: str, item_type: str) -> None:
        nonlocal list_items, list_type
        if list_items and list_type != item_type:
            flush_list()
        list_type = item_type
        list_items.append(item)

    for raw_line in report_markdown.splitlines():
        stripped_line = raw_line.strip()
        if _is_markdown_table_line(stripped_line):
            flush_list()
            table_rows.append(stripped_line)
            continue

        flush_table()
        line = _markdown_to_reportlab_text(stripped_line)
        if not line:
            flush_list()
            story.append(Spacer(1, 5))
            continue
        if line.startswith("- ") or line.startswith("* "):
            append_list_item(line[2:].strip(), "bullet")
            continue
        flush_list()
        if line.startswith("# "):
            story.append(Paragraph(line[2:].strip(), title_style))
        elif line.startswith("## "):
            story.append(Paragraph(line[3:].strip(), heading1_style))
        elif line.startswith("### "):
            story.append(Paragraph(line[4:].strip(), heading2_style))
        elif set(line) <= {"-", "_", "*"}:
            story.append(Spacer(1, 8))
        else:
            story.append(Paragraph(line, body_style))

    flush_table()
    flush_list()
    if not story:
        raise RuntimeError("No report content available for PDF generation.")
    doc.build(story)
    return buffer.getvalue()


def _is_markdown_table_line(value: str) -> bool:
    return value.startswith("|") and value.endswith("|") and value.count("|") >= 2


def _is_markdown_table_separator(value: str) -> bool:
    cells = _split_table_row(value)
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells
    )


def _split_table_row(value: str) -> list[str]:
    return [cell.strip() for cell in value.strip().strip("|").split("|")]


def _markdown_to_reportlab_text(value: str) -> str:
    value = escape(value)
    value = re.sub(r"^(\d+)\.\s+", r"\1.&nbsp;", value)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", value)
    return re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<link href="\2" color="blue">\1</link>',
        value,
    )

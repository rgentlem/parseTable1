"""PDF rendering for synthetic Table 1 documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from table1_parser.synthetic.spec_models import SyntheticDocumentSpec, expand_display_rows


_EMBEDDED_SPEC_PATTERN = re.compile(
    r'<script id="synthetic-table-spec" type="application/json">(.*?)</script>',
    flags=re.DOTALL,
)


@dataclass(frozen=True)
class TableRowLayout:
    """Finalized table row box used for text placement and borders."""

    row_type: str
    top_y: float
    bottom_y: float
    text_top_y: float
    label_lines: list[str]
    value_lines: list[list[str]]
    indent_level: int


@dataclass(frozen=True)
class TableLayout:
    """Finalized table geometry derived from wrapped row content."""

    table_left: float
    table_right: float
    column_starts: list[float]
    first_col_width: float
    other_col_width: float
    header: TableRowLayout
    body_rows: list[TableRowLayout]


def _wrap_text(text: str, max_width: float, font_size: float) -> list[str]:
    if not text:
        return [""]
    approx_char_width = font_size * 0.52
    max_chars = max(1, int(max_width / approx_char_width))
    words = text.split()
    if not words:
        return [text]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _row_layout(
    *,
    row_type: str,
    label: str,
    values: list[str],
    top_y: float,
    first_col_width: float,
    other_col_width: float,
    font_size: float,
    line_gap: float,
    indent_level: int,
) -> TableRowLayout:
    cell_padding_y = 5.0
    indent_offset = indent_level * 14.0
    label_lines = _wrap_text(label, max_width=first_col_width - indent_offset, font_size=font_size)
    value_lines = [_wrap_text(value, other_col_width, font_size) for value in values]
    content_lines = max(1, len(label_lines), *(len(lines) for lines in value_lines))
    row_height = (cell_padding_y * 2) + (content_lines * line_gap)
    text_top_y = top_y - cell_padding_y - font_size
    return TableRowLayout(
        row_type=row_type,
        top_y=top_y,
        bottom_y=top_y - row_height,
        text_top_y=text_top_y,
        label_lines=label_lines,
        value_lines=value_lines,
        indent_level=indent_level,
    )


def render_pdf_from_html(html: str, output_path: str | Path) -> Path:
    """Render a synthetic document PDF from the generated HTML."""
    match = _EMBEDDED_SPEC_PATTERN.search(html)
    if not match:
        raise ValueError("Synthetic spec payload not found in HTML.")
    spec = SyntheticDocumentSpec.model_validate_json(match.group(1))
    page_width = 612.0
    page_height = 792.0
    margin_x = 54.0
    margin_y = 54.0
    line_gap = 14.0
    font_size = 11.0
    content: list[str] = []
    current_y = page_height - margin_y

    def add_text(x: float, y: float, text: str, size: float = font_size) -> None:
        escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content.append(f"BT /F1 {size:.2f} Tf {x:.2f} {y:.2f} Td ({escaped_text}) Tj ET")

    def add_line(x1: float, y1: float, x2: float, y2: float, width: float = 1.0) -> None:
        content.append(f"{width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def advance(lines: int = 1, extra: float = 0.0) -> None:
        nonlocal current_y
        current_y -= (lines * line_gap) + extra

    def write_wrapped_block(text: str, *, size: float = font_size, width: float = page_width - (2 * margin_x)) -> None:
        for line in _wrap_text(text, width, size):
            add_text(margin_x, current_y, line, size=size)
            advance()

    add_text(margin_x, current_y, spec.document_title, size=14.0)
    advance(extra=4.0)
    if spec.subtitle:
        write_wrapped_block(spec.subtitle, size=11.0)
    for paragraph in spec.paragraphs:
        write_wrapped_block(paragraph)
        advance(extra=4.0)
    add_text(margin_x, current_y, spec.table_caption, size=12.0)
    advance(extra=8.0)

    table_top_y = page_height - margin_y
    table_top_y -= line_gap + 4.0
    if spec.subtitle:
        table_top_y -= len(_wrap_text(spec.subtitle, page_width - (2 * margin_x), font_size)) * line_gap
    for paragraph in spec.paragraphs:
        table_top_y -= len(_wrap_text(paragraph, page_width - (2 * margin_x), font_size)) * line_gap
        table_top_y -= 4.0
    table_top_y -= line_gap + 8.0

    table_width = page_width - (2 * margin_x)
    first_col_width = table_width * 0.40
    other_col_width = (table_width - first_col_width) / max(1, len(spec.columns) - 1)
    col_widths = [first_col_width] + [other_col_width] * max(0, len(spec.columns) - 1)
    column_starts = [margin_x]
    for width in col_widths[:-1]:
        column_starts.append(column_starts[-1] + width)
    header = _row_layout(
        row_type="header",
        label=spec.columns[0],
        values=spec.columns[1:],
        top_y=table_top_y,
        first_col_width=first_col_width,
        other_col_width=other_col_width,
        font_size=font_size,
        line_gap=line_gap,
        indent_level=0,
    )
    body_rows: list[TableRowLayout] = []
    current_top = header.bottom_y
    for row in expand_display_rows(spec):
        layout = _row_layout(
            row_type=row.row_type,
            label=row.label,
            values=row.values,
            top_y=current_top,
            first_col_width=first_col_width,
            other_col_width=other_col_width,
            font_size=font_size,
            line_gap=line_gap,
            indent_level=row.indent_level,
        )
        body_rows.append(layout)
        current_top = layout.bottom_y
    table_layout = TableLayout(
        table_left=margin_x,
        table_right=margin_x + table_width,
        column_starts=column_starts,
        first_col_width=first_col_width,
        other_col_width=other_col_width,
        header=header,
        body_rows=body_rows,
    )
    for row in [table_layout.header, *table_layout.body_rows]:
        indent_offset = row.indent_level * 14.0
        row_line_count = max(1, len(row.label_lines), *(len(lines) for lines in row.value_lines))
        for line_idx in range(row_line_count):
            line_y = row.text_top_y - (line_idx * line_gap)
            label_text = row.label_lines[line_idx] if line_idx < len(row.label_lines) else ""
            add_text(table_layout.column_starts[0] + indent_offset, line_y, label_text)
            for value_idx in range(len(spec.columns) - 1):
                line_text = ""
                if value_idx < len(row.value_lines) and line_idx < len(row.value_lines[value_idx]):
                    line_text = row.value_lines[value_idx][line_idx]
                add_text(table_layout.column_starts[value_idx + 1], line_y, line_text)
    if spec.layout.horizontal_rules:
        add_line(table_layout.table_left, table_layout.header.top_y, table_layout.table_right, table_layout.header.top_y, width=1.5)
        add_line(table_layout.table_left, table_layout.header.bottom_y, table_layout.table_right, table_layout.header.bottom_y, width=1.5)
        for row in table_layout.body_rows:
            if row.row_type == "section_header":
                add_line(table_layout.table_left, row.top_y, table_layout.table_right, row.top_y, width=0.8)
        if table_layout.body_rows:
            add_line(
                table_layout.table_left,
                table_layout.body_rows[-1].bottom_y,
                table_layout.table_right,
                table_layout.body_rows[-1].bottom_y,
                width=1.5,
            )
    current_y = table_layout.body_rows[-1].bottom_y if table_layout.body_rows else table_layout.header.bottom_y
    if spec.footnotes:
        advance(extra=6.0)
        for note in spec.footnotes:
            write_wrapped_block(f"* {note}", size=10.0)

    stream = "\n".join(content)
    content_bytes = stream.encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {int(page_width)} {int(page_height)}] "
            f"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ).encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content_bytes)} >>\nstream\n".encode("ascii") + content_bytes + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_index, object_bytes in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_index} 0 obj\n".encode("ascii"))
        output.extend(object_bytes)
        output.extend(b"\nendobj\n")
    xref_start = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("ascii")
    )
    pdf_path = Path(output_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(bytes(output))
    return pdf_path

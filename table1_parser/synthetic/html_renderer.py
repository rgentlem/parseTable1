"""HTML rendering for synthetic Table 1 documents."""

from __future__ import annotations

from html import escape

from table1_parser.synthetic.spec_models import SyntheticDocumentSpec, expand_display_rows, spec_to_json


def render_html_document(spec: SyntheticDocumentSpec) -> str:
    """Return an HTML document for a synthetic Table 1-style PDF source."""

    display_rows = expand_display_rows(spec)
    n_cols = len(spec.columns)
    rule_class = "table--rules" if spec.layout.horizontal_rules else "table--plain"
    paragraphs_html = "".join(f"<p>{escape(paragraph)}</p>" for paragraph in spec.paragraphs)
    subtitle_html = f'<p class="subtitle">{escape(spec.subtitle)}</p>' if spec.subtitle else ""
    footnotes_html = "".join(f"<li>{escape(note)}</li>" for note in spec.footnotes)
    row_html_parts: list[str] = []
    for row in display_rows:
        row_classes = ["table-row", f"row-{row.row_type}"]
        if row.indent_level:
            row_classes.append("level-indented")
        label_class = "label-cell wrap-label" if spec.layout.wrapped_labels else "label-cell"
        label_style = f' style="padding-left: {row.indent_level * 1.5:.1f}rem;"' if row.indent_level else ""
        cells = [f'<td class="{label_class}"{label_style}>{escape(row.label)}</td>']
        for value in row.values[: n_cols - 1]:
            cells.append(f"<td>{escape(value)}</td>")
        while len(cells) < n_cols:
            cells.append("<td></td>")
        row_html_parts.append(f'<tr class="{" ".join(row_classes)}">{"".join(cells)}</tr>')
    rows_html = "".join(row_html_parts)
    columns_html = "".join(f"<th>{escape(column)}</th>" for column in spec.columns)
    embedded_spec = spec_to_json(spec)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(spec.document_title)}</title>
  <style>
    body {{ font-family: Helvetica, Arial, sans-serif; margin: 2rem; color: #111; }}
    h1 {{ font-size: 1.2rem; margin-bottom: 0.3rem; }}
    .subtitle {{ color: #444; margin-top: 0; }}
    .caption {{ font-weight: 700; margin-top: 1rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
    th, td {{ padding: 0.3rem 0.5rem; text-align: left; vertical-align: top; }}
    .table--rules thead tr {{ border-top: 2px solid #222; border-bottom: 2px solid #222; }}
    .table--rules tbody tr.row-section_header td {{ border-top: 1px solid #666; font-weight: 700; }}
    .table--rules tbody tr:last-child {{ border-bottom: 2px solid #222; }}
    .wrap-label {{ max-width: 18rem; white-space: normal; }}
    .label-cell {{ width: 40%; }}
    .footnotes {{ margin-top: 1rem; padding-left: 1.25rem; }}
  </style>
</head>
<body>
  <h1>{escape(spec.document_title)}</h1>
  {subtitle_html}
  {paragraphs_html}
  <p class="caption">{escape(spec.table_caption)}</p>
  <table class="{rule_class}">
    <thead>
      <tr>{columns_html}</tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
  <ul class="footnotes">{footnotes_html}</ul>
  <script id="synthetic-table-spec" type="application/json">{embedded_spec}</script>
</body>
</html>
"""

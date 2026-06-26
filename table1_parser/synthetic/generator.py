"""Orchestration for synthetic Table 1 document generation."""

from __future__ import annotations

import json
from pathlib import Path

from table1_parser.synthetic.html_renderer import render_html_document
from table1_parser.synthetic.pdf_renderer import render_pdf_from_html
from table1_parser.synthetic.spec_models import load_table_spec
from table1_parser.synthetic.truth_writer import build_truth_json


def generate_synthetic_document(
    spec_path: str | Path,
    output_prefix: str | Path,
    *,
    write_html: bool = True,
) -> dict[str, Path]:
    """Generate a synthetic PDF, matching truth JSON, and optionally HTML."""

    spec = load_table_spec(spec_path)
    html = render_html_document(spec)
    truth_payload = build_truth_json(spec)

    prefix = Path(output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, Path] = {}
    if write_html:
        html_path = prefix.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")
        outputs["html"] = html_path

    pdf_path = render_pdf_from_html(html, prefix.with_suffix(".pdf"))
    outputs["pdf"] = pdf_path

    truth_path = prefix.with_name(f"{prefix.name}_truth").with_suffix(".json")
    truth_path.write_text(json.dumps(truth_payload, indent=2), encoding="utf-8")
    outputs["truth_json"] = truth_path
    return outputs


__all__ = ["generate_synthetic_document", "load_table_spec", "render_html_document", "render_pdf_from_html", "build_truth_json"]

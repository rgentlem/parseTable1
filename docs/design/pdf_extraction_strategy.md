# PDF Extraction Strategy

## Purpose

This document defines the PDF extraction strategy for the Table 1 parsing project.

The key design principle is:

**Choose the primary extracted representation based on downstream use.**

This project has three different downstream needs:
- document text for RAG
- tables for structured parsing
- figures for visual extraction

These should not be forced into one representation.

---

# Primary Design Decision

## Narrative document text
Primary representation: **ordered `PaperDocument.prose` blocks**

Use block-owned `PaperSection` records for:
- titles
- abstract
- section text
- chunking
- embedding
- RAG

Reason:
`PaperDocument` preserves canonical block order and explicit prose, entity, or
residual ownership while retaining source line IDs into positioned evidence.
Markdown remains a derived human-readable view of prose ownership; it does not
define section structure.

## Tables
Primary representation: **JSON / structured table objects**

Use JSON for:
- row / column structure
- cells
- headers
- variable rows
- categorical levels
- diagnostics
- validation

Reason:
Tables are structured objects. JSON preserves structure far better than Markdown for parsing workflows.

Markdown may still be generated for table debugging or human inspection, but it is **not** the primary internal representation for tables.

## Figures
Primary representation: **images**
- PNG preferred
- PDF region outputs acceptable if already supported

Reason:
Figures are visual artifacts and should be handled as images, not reduced to Markdown.

---

# Extractor Choice

The default extractor should be:

**PyMuPDF4LLM**

Keep `pymupdf4llm` as the only extractor.

PyMuPDF4LLM supports:
- Markdown output
- JSON output
- layout-aware extraction
- image and vector extraction
- structured output useful for LLM/RAG workflows

The current parser does not use PyMuPDF4LLM markdown for paper context.
`paper_positioned_document.json` is the shared PyMuPDF positioned-geometry pass
for lines, spans, words, characters, page text, and horizontal rule segments.
`paper_document.json` is the canonical block and ownership representation.
Table extraction and other non-prose consumers read its text, role, and order,
joining source IDs to the positioned document for raw lines, spans, characters,
and rules. `paper_markdown.md` and `paper_sections.json` are prose-only views
over it. There is no separate full-paper text-stream artifact.

---

# Extraction Strategy by Content Type

## 1. Narrative text extraction
Persisted positioned-text evidence:

PDF
→ `paper_positioned_document.json`
→ `paper_document.json`
→ `paper_sections.json` + `paper_markdown.md`

Parser document-context path:

PDF
→ positioned PyMuPDF text lines
→ `paper_document.json`
→ `paper_sections.json`
→ bibliography, visual-reference, variable-inventory, and table-context
artifacts

`PaperDocument` is the source of truth for canonical document order and
ownership; `PaperPositionedDocument` is the source of truth for raw PDF text and
geometry.

## 2. Table extraction
Preferred path:

PDF
→ structured extraction / JSON
→ normalization
→ heuristics
→ optional LLM table refinement
→ validation

If PyMuPDF4LLM JSON output is useful for table-sensitive extraction or layout debugging, use it.
If existing table code already operates on JSON, preserve that architecture.

Do not change the table pipeline to Markdown-first.

When PyMuPDF4LLM emits an oversized table box that mixes upright article text
with a rotated table region, the extractor may derive a separate table
candidate from the contiguous rotated PyMuPDF text block inside that box. The
derived candidate uses positioned words/chars and rule geometry, records
`orientation_strategy = "rotated_text_block_from_mixed_table_box"`, and
competes with the original backend box through normal candidate deduplication.
This keeps the primary backend but prevents a backend table-box regression from
pulling non-table body text into the table grid.

PyMuPDF character extraction also performs narrow, font-qualified symbol
normalization before word/grid reconstruction. Known embedded symbol-font codes
such as plus-minus, multiplication, minus, and comparator glyphs are converted
to Unicode while preserving raw glyph provenance on character records.

## 3. Figure extraction
Preferred path:

PDF
→ extracted image / vector region
→ PNG (preferred)
→ optional metadata JSON

If the extraction layer supports figure metadata, keep it lightweight.

---

# Extractor Priority Order

Use extractors in this order:

1. **Primary:** PyMuPDF4LLM
2. Improve the existing `pymupdf4llm` extractor

Fallback should only be used if:
- PyMuPDF4LLM fails
- PyMuPDF4LLM output is unusable for the requested artifact
- the primary extractor is explicitly disabled by configuration

Do not treat the fallback as co-equal with the primary path.

---

# Content-Type-Aware Output Policy

The extraction layer should expose or preserve different output types depending on what is being extracted.

## Narrative content output
- Markdown

## Table content output
- JSON / structured table representation

## Figure content output
- PNG or equivalent image artifact
- optional lightweight metadata

This distinction is intentional and should be preserved in code.

---

# Debugging and Diagnostics

Diagnostics should make it clear:
- which extractor ran
- whether fallback was used
- what artifact was produced:
  - Markdown
  - JSON
  - image output

For debugging extraction problems it should be possible to inspect:
- narrative Markdown
- table JSON
- figure artifacts
- extractor choice
- fallback status

Do not silently change extraction mode without surfacing it.

---

# Header / Footer Handling

If repeated page headers/footers should be removed, apply that logic primarily to the **narrative Markdown path**.

Do not assume table extraction should be cleaned the same way as narrative text.
Narrative cleanup and table structure preservation are different concerns.

---

# Implementation Guidance

Keep extraction modular.

Recommended shape:
- one extraction interface
- one default PyMuPDF4LLM implementation
- one or more fallback implementations
- downstream code depends on extraction interfaces and content-type-specific outputs

Do not spread extractor-specific logic through unrelated parsing modules.

---

# Testing Guidance

Add or maintain tests that confirm:

1. PyMuPDF4LLM remains the default table extraction backend
2. positioned PyMuPDF text produces layout-aware document order
3. `paper_markdown.md` remains a rendered prose view of `paper_document.json`,
   not a separate backend extraction path
4. table extraction preserves JSON / structured output
5. figure extraction produces image artifacts when applicable
6. diagnostics record extractor choice and output type

Keep fixtures small.
Do not add large generated artifacts to the repository.

---

# Non-Goals

This strategy does not require:
- converting tables to Markdown as the primary internal representation
- converting figures into Markdown
- replacing all downstream parser logic
- removing all fallback extractors
- redesigning the entire project

---

# Summary

The extraction strategy is:

- **PyMuPDF4LLM remains the default table extraction backend**
- **Positioned PyMuPDF text is primary for parser document order**
- **Paper markdown is rendered from the positioned text stream, not extracted
  through a second backend fallback**
- **JSON is primary for tables**
- **PNG/image artifacts are primary for figures**
- **the representation is chosen by downstream purpose, not forced globally**

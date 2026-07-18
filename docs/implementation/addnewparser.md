# AGENTS.md

This repository parses epidemiology-style PDF documents and extracts structured information from narrative text, tables, and figures.

The current priority is improving PDF extraction quality by making **PyMuPDF4LLM** the primary extractor while preserving the correct downstream representation for each content type.

Read this file before implementing changes.

---

# Core Representation Policy

Different content types must use different primary representations.

## 1. Narrative document text
Use **Markdown** as the primary representation for:
- title / abstract / sections
- chunking
- embedding
- RAG workflows

Expected flow:

PDF
→ Markdown
→ sectioning / chunking
→ embeddings / retrieval

## 2. Tables
Use **structured JSON** as the primary representation for:
- table extraction
- row / column structure
- cell values
- row typing
- variable / level parsing
- diagnostics
- validation

Expected flow:

PDF
→ structured table JSON
→ normalization
→ heuristics
→ optional LLM refinement
→ validation

Do **not** switch the table pipeline to Markdown-first.
Markdown may be useful for debugging or human viewing, but **JSON remains the primary internal representation for tables**.

## 3. Figures
Use **image artifacts** as the primary representation for figures:
- PNG preferred for extracted figures / cropped figure regions
- PDF region output acceptable if already supported internally

Expected flow:

PDF
→ figure extraction
→ PNG (or equivalent image artifact)
→ downstream figure handling

---

# Primary PDF Extraction Policy

Use **PyMuPDF4LLM** as the default PDF extraction path.

Rationale:
- it supports Markdown output
- it supports JSON output
- its JSON output includes layout / bounding box information
- it supports image and vector extraction
- it is well suited for LLM/RAG-oriented document extraction

Keep extraction aligned with the current `pymupdf4llm`-based path.

---

# Extraction Strategy by Content Type

## Narrative text extraction
Use **positioned PyMuPDF text** as the default parser document-order source for
document text and sections. Do not add a PyMuPDF4LLM Markdown fallback for
paper context.

Preferred parser document-order API:
- PyMuPDF page text lines with bboxes

Persisted document-context evidence API:
- `paper_positioned_document.json`
- `paper_document.json`
- rendered `paper_markdown.md`

The parser should derive `paper_document.json` from positioned PyMuPDF text,
apply page-furniture filtering, detect page column bands, and order text as
page, column, then vertical position. Markdown can still be useful for
inspection, chunking, or embedding, but it should be rendered from the
canonical document rather than extracted through a second backend path.

## Table extraction
Use **structured JSON** as the default extracted artifact for tables.

Prefer extraction paths that preserve:
- rows
- columns
- headers
- cells
- coordinates / bounding boxes when available

If PyMuPDF4LLM JSON is used for table-sensitive extraction/debugging, that is appropriate.
If downstream table code already expects JSON, preserve that design.

Do not force tables through a Markdown-only representation.

## Figure extraction
Use image extraction for figures.

Preferred outputs:
- PNG files
- optional metadata JSON if available

---

# Required extractor priority order

Use extractors in this order:

1. **Primary:** PyMuPDF4LLM
2. Extend the existing `pymupdf4llm` path when needed

Fallback extractors should only run when:
- the primary extractor fails
- the primary extractor returns unusable output
- the primary extractor is explicitly disabled

Do not treat all extractors as co-equal.

PyMuPDF4LLM is the default.
No legacy extraction backend should remain as backup.

---

# Architecture Rules

Keep extraction modular.

Recommended design:
- one extraction interface
- one PyMuPDF4LLM implementation as default
- one or more fallback extractor implementations
- downstream code depends on the extraction interface, not directly on a specific extractor library

Do not spread extractor-specific calls throughout unrelated modules.

Do not redesign the parser architecture unless explicitly asked.

---

# Representation Rules for Codex

When changing code, preserve these assumptions:

## Narrative parser / chunking code
Should consume Markdown.

## Table parser / normalization / heuristics / LLM table refinement
Should consume JSON / structured table objects.

## Figure handling
Should consume image artifacts plus lightweight metadata.

If a debug script or visualization helper needs alternate formats, that is fine — but do not replace the primary internal representation for the content type.

---

# Header / Footer Handling

If the extractor supports suppressing repeated headers and footers for narrative Markdown extraction, keep that configurable.

Do not assume the same header/footer behavior applies identically to table JSON extraction.

Narrative Markdown cleaning and table structure preservation are different concerns.

---

# Diagnostics

Diagnostics should record:
- which extractor ran
- whether fallback was used
- which primary representation was produced:
  - Markdown for narrative
  - JSON for tables
  - image artifact for figures

Do not silently switch extractor paths without making that visible.

---

# Testing Requirements

When implementing extraction changes, add tests that confirm:

1. PyMuPDF4LLM is the default extractor
2. `pymupdf4llm` is the only extraction backend
3. narrative extraction produces Markdown
4. table extraction preserves structured JSON
5. figure extraction produces image artifacts when applicable
6. diagnostics record extractor choice and fallback behavior

Keep fixtures small.
Do not commit large generated artifacts.

---

# Scope Control

When asked to improve extraction:
- keep the work focused on extraction modules and closely related normalization/debugging
- do not redesign the whole parser
- do not switch the table pipeline from JSON to Markdown
- do not add a second extraction backend unless explicitly asked

---

# Coding Style

Prefer:
- small focused modules
- explicit extractor interfaces
- deterministic fallback behavior
- clear logging
- preserving downstream representation by content type

Avoid:
- using one representation for everything
- broad refactors unrelated to extraction
- making the fallback path the de facto primary path

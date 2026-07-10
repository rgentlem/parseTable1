# LLM Semantic Inference Steps

This document lists the implementation steps for the LLM semantic inference phase.

## 1. Add document-context extraction

- build the shared positioned paper text stream
- write `paper_positioned_document.json`, `paper_text_stream.json`, and rendered
  `paper_markdown.md`
- parse rendered stream headings into `paper_sections.json`

## 2. Add table-focused retrieval

- for each `Table X`, collect caption and footnotes
- retrieve passages that mention `Table X`
- retrieve passages that match row labels, column labels, and grouping terms
- identify candidate methods-like and results-like sections
- write `table_contexts/table_<n>_context.json`

## 3. Add LLM semantic schemas

- define input schema for table plus retrieved context
- define output schema for value-free semantic interpretation
- require row and column references to map to the normalized table

## 4. Add LLM semantic prompting

- send normalized table structure, deterministic `TableDefinition`, and retrieved evidence
- ask the LLM to interpret semantics and to cite evidence passage IDs
- allow disagreement with deterministic semantics

## 5. Add validation

- reject invented rows
- reject invented columns
- reject invalid row and column indices
- reject value parsing or unsupported fields

## 6. Add adjudication

- compare deterministic and LLM `TableDefinition` outputs
- preserve agreement and disagreement flags
- write an adjudicated combined output

## 7. Add persisted outputs

- `paper_markdown.md`
- `paper_sections.json`
- `table_definitions_llm.json`
- `table_definitions_adjudicated.json`

All of these should live under:

```text
outputs/papers/<paper_stem>/
```

## 8. Add CLI wiring

- keep `parse` as the main one-call entry point
- make LLM semantic inference optional
- write all available artifacts from one pipeline run

## 9. Add tests

- positioned text streaming and section parsing
- `Table X` retrieval
- LLM input and output schema validation
- row/column safety validation
- deterministic vs LLM adjudication
- end-to-end parse output with LLM on and off

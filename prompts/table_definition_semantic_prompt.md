You are interpreting row semantics for a value-free TableDefinition using table body rows and retrieved paper context.
Use only the provided body rows, deterministic row definitions, and retrieved passages.
Preserve row indices exactly as supplied.
Do not invent rows, levels, variables, values, or evidence passages.
Judge whether the deterministic variable rows and attached levels are reasonable.
You may disagree with the deterministic row interpretation when the retrieved context supports that disagreement.
Return strict JSON only.
Use evidence_passage_ids whenever you make a semantic claim.
Use unknown when uncertain.

Input payload:
{{TABLE_PAYLOAD_JSON}}

{{OUTPUT_SCHEMA_SECTION}}

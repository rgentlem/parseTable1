# LLM Integration

The repository no longer runs any LLM call during `table1-parser parse`.

Current implemented flow:

`NormalizedTable -> TableDefinition -> ParsedTable`

The deterministic pipeline still writes the paper-context artifacts that a later LLM workflow may use:

- `paper_markdown.md`
- `paper_sections.json`
- `paper_variable_inventory.json`
- `table_contexts/*.json`

## Active LLM Path

The current active LLM feature is a separate review command:

```bash
table1-parser review-variable-plausibility path/to/paper.pdf
```

This command reruns the deterministic pipeline, writes the same deterministic artifacts as `parse`, and then optionally runs a narrow QA-style LLM review for descriptive-characteristics tables.

Current LLM flow:

`TableDefinition.variables -> LLMVariablePlausibilityTableReview`

Scope:

- judge whether `variable_type` fits the variable label
- judge whether categorical levels are sensible for the named variable
- score each variable with `plausibility_score` in `[0, 1]`

Non-scope:

- row rewriting
- column rewriting
- grouping-label reinterpretation
- cross-table prompting
- parse-time automatic correction of `TableDefinition`

## Persisted LLM Artifacts

The standalone review command writes:

- `table_variable_plausibility_llm.json`

When `LLM_DEBUG=true`, it also writes:

```text
outputs/papers/<paper_stem>/llm_variable_plausibility_debug/<timestamp>/
  llm_variable_plausibility_monitoring.json
  table_0/
    variable_plausibility_llm_input.json
    variable_plausibility_llm_metrics.json
    variable_plausibility_llm_output.json
    variable_plausibility_llm_review.json
```

These are inspection artifacts only and should not be committed. `outputs/` is ignored by Git.

## Provider Support

The repository currently supports:

- `LLM_PROVIDER=openai`
- `LLM_PROVIDER=qwen`

The configured client uses:

- environment variables for credentials and model selection
- provider-specific request handling
- structured output parsed into `LLMVariablePlausibilityTableReview`

OpenAI uses:

- the official OpenAI Python SDK
- native structured parsing into the plausibility-review Pydantic response model
- prompt compaction by omitting the explicit schema block from the prompt

Qwen uses:

- direct HTTP requests to DashScope
- a compact JSON-only output contract
- local JSON parsing plus Pydantic validation

## Environment Variables

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=your_api_key_here
export OPENAI_MODEL=gpt-5.5
export LLM_TIMEOUT_SECONDS=60
export LLM_MAX_RETRIES=2
export LLM_DEBUG=false
export LLM_SDK_DEBUG=false
```

For `gpt-5.5` and other OpenAI reasoning-model IDs that reject custom sampling parameters, the client omits `temperature` and uses provider defaults.

Required for OpenAI:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`

Required for Qwen:

- `DASHSCOPE_API_KEY`
- `QWEN_MODEL`

Optional for Qwen:

- `QWEN_BASE_URL`

Debug note:

- set `LLM_DEBUG=true` to write timestamped variable-plausibility debug artifacts during `review-variable-plausibility`
- set `LLM_SDK_DEBUG=true` only if you want verbose OpenAI SDK/provider logging in the terminal

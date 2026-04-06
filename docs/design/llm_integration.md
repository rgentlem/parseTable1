# LLM Integration

The repository's active LLM path is the row-focused semantic post-`TableDefinition` layer used by `table1-parser parse`.

Current flow:

`NormalizedTable -> TableDefinition -> TableContext -> LLMSemanticTableDefinition`

The LLM is used only for optional row interpretation after deterministic table-definition assembly and paper-context retrieval.

Current scope:

- row variables
- categorical levels under those variables
- evidence passage attribution for row claims

Current non-scope:

- column reinterpretation
- grouping-label reinterpretation
- cross-table prompting

Current prompt-shaping strategy:

- compact row hints rather than full cell arrays
- compact deterministic variable spans rather than full `TableDefinition` dumps
- a small truncated passage bundle rather than the full retrieval payload

## Current provider path

The repository currently supports:

- `LLM_PROVIDER=openai`
- `LLM_PROVIDER=qwen`

The configured client uses:

- environment variables for credentials and model selection
- provider-specific request handling
- structured output parsed into `LLMSemanticTableDefinition`

OpenAI uses:

- the official OpenAI Python SDK
- native structured parsing into the semantic Pydantic response model
- provider-aware prompt compaction, so the prompt does not duplicate the full output schema text

Qwen uses:

- direct HTTP requests to DashScope
- a compact JSON-only output contract
- local JSON parsing plus the semantic Pydantic validation layer

## Environment variables

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=your_api_key_here
export OPENAI_MODEL=gpt-4.1-mini
export LLM_TEMPERATURE=0
export LLM_TIMEOUT_SECONDS=60
export LLM_MAX_RETRIES=2
export LLM_DEBUG=false
export LLM_SDK_DEBUG=false
```

Required for OpenAI:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`

Required for Qwen:

- `DASHSCOPE_API_KEY`
- `QWEN_MODEL`

Optional for Qwen:

- `QWEN_BASE_URL`

Debug note:

- set `LLM_DEBUG=true` to write timestamped semantic-LLM debug artifacts during `table1-parser parse`
- these artifacts include per-table timing, payload-size summaries, raw structured responses, and validated interpretations when available
- set `LLM_SDK_DEBUG=true` only if you want verbose OpenAI SDK/provider logging in the terminal

## CLI usage

```bash
table1-parser parse path/to/paper.pdf
```

To disable the semantic LLM stage explicitly:

```bash
table1-parser parse path/to/paper.pdf --no-llm-semantic
```

## Debug artifacts

When `LLM_DEBUG=true`, semantic debug artifacts are written under:

```text
outputs/papers/<paper_stem>/llm_semantic_debug/<timestamp>/
  llm_semantic_monitoring.json
  table_0/
    table_definition_llm_input.json
    table_definition_llm_metrics.json
    table_definition_llm_output.json
    table_definition_llm_interpretation.json
```

These are inspection artifacts only and should not be committed. `outputs/` is ignored by Git.

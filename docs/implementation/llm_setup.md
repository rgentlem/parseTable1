# LLM Setup

This project supports one optional provider-backed LLM workflow:

- `table1-parser review-variable-plausibility`

The deterministic `table1-parser parse` command does not call an LLM.

## Required Variables

When `LLM_PROVIDER=openai`, these must be set:

- `LLM_PROVIDER`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`

When `LLM_PROVIDER=qwen`, these must be set:

- `LLM_PROVIDER`
- `DASHSCOPE_API_KEY`
- `QWEN_MODEL`

Optional:

- `LLM_TEMPERATURE`
- `LLM_TIMEOUT_SECONDS`
- `LLM_MAX_RETRIES`
- `LLM_DEBUG`
- `LLM_SDK_DEBUG`
- `QWEN_BASE_URL`

## Example Setup On macOS/Linux

OpenAI:

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

Qwen:

```bash
export LLM_PROVIDER=qwen
export DASHSCOPE_API_KEY=your_api_key_here
export QWEN_MODEL=qwen-plus
export QWEN_BASE_URL=https://dashscope.aliyuncs.com/api/v1
export LLM_TEMPERATURE=0
export LLM_TIMEOUT_SECONDS=60
export LLM_MAX_RETRIES=2
export LLM_DEBUG=false
```

## Example Setup On Windows PowerShell

OpenAI:

```powershell
$env:LLM_PROVIDER = "openai"
$env:OPENAI_API_KEY = "your_api_key_here"
$env:OPENAI_MODEL = "gpt-4.1-mini"
$env:LLM_TEMPERATURE = "0"
$env:LLM_TIMEOUT_SECONDS = "60"
$env:LLM_MAX_RETRIES = "2"
$env:LLM_DEBUG = "false"
$env:LLM_SDK_DEBUG = "false"
```

Qwen:

```powershell
$env:LLM_PROVIDER = "qwen"
$env:DASHSCOPE_API_KEY = "your_api_key_here"
$env:QWEN_MODEL = "qwen-plus"
$env:QWEN_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
$env:LLM_TEMPERATURE = "0"
$env:LLM_TIMEOUT_SECONDS = "60"
$env:LLM_MAX_RETRIES = "2"
$env:LLM_DEBUG = "false"
```

Meaning of the two debug flags:

- `LLM_DEBUG=true`
  write timestamped variable-plausibility debug JSON artifacts to disk during `review-variable-plausibility`
- `LLM_SDK_DEBUG=true`
  enable verbose provider/SDK logging in the terminal

## Install Requirement

The configured OpenAI client requires the OpenAI Python SDK:

```bash
python3 -m pip install -e '.[dev]'
```

The configured Qwen client uses the Python standard library HTTP stack.

If provider setup is missing, `review-variable-plausibility` skips provider calls with a clear setup warning and writes an empty review artifact.

## Running The Configured LLM Path

```bash
table1-parser review-variable-plausibility path/to/paper.pdf
```

## Debug Artifacts

If you want per-table review debug artifacts, enable:

```bash
export LLM_DEBUG=true
```

Then run `table1-parser review-variable-plausibility ...`. The parser writes a timestamped debug directory under:

```text
outputs/papers/<paper_stem>/llm_variable_plausibility_debug/
```

## Security

- Do not hardcode API keys in source files.
- Do not commit API keys to the repository.
- Prefer setting credentials in the shell environment or a local untracked secrets file loaded by your shell.

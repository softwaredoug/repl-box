# Contributing

Thanks for helping improve repl-box. This guide covers the local dev workflow.

## Requirements

- Python 3.12+
- uv

## Setup

Install dependencies (including dev/test extras):

```bash
uv sync --dev
```

## Running tests

Run the full test suite:

```bash
uv run pytest
```

Run a single test file:

```bash
uv run pytest tests/test_jupyter_e2e.py
```

Run integration tests only:

```bash
uv run pytest -m integration
```

## Jupyter E2E tests

Integration tests execute VS Code-style cell files stored in
`tests/resources/jupyter_cells/*.py`. Cells are delimited by `# %%` headers.

Expectation directives:

- `# %% EXPECT: <text>`
- `# %% EXPECT-RE: <regex>`
- `# %% EXPECT-ERR: <text>`

If a cell has no EXPECT directives it must run without errors.

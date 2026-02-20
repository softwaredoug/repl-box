# repl-box

A sandboxed Python REPL server for agents. Runs as a separate process and communicates over a Unix domain socket.

## Purpose

Agents (e.g. Claude, LLM tools) need a way to execute Python code snippets with persistent state — like a real REPL — without running code in-process. `repl-box` provides:

- A long-lived subprocess with its own Python interpreter
- Stateful execution: variables, imports, and definitions persist across calls
- Captured stdout/stderr returned to the caller
- A clean socket-based interface any language can use

## Architecture

```
Agent Process
    |
    | (Unix socket: /tmp/repl-box.sock)
    v
repl-box server (separate process)
    |
    | exec() in persistent namespace
    v
Python REPL state (globals dict, maintained across calls)
```

## Protocol

Newline-delimited JSON over a Unix domain socket.

**Request:**
```json
{"code": "x = 1 + 1\nprint(x)"}
```

**Response:**
```json
{"stdout": "2\n", "stderr": "", "error": null}
```

If the code raises an exception:
```json
{"stdout": "", "stderr": "", "error": "NameError: name 'y' is not defined"}
```

## Project Layout

```
repl-box/
  server.py     # The REPL server (run as a subprocess)
  client.py     # Thin client for sending code and receiving output
  main.py       # Entry point (uv run)
  pyproject.toml
  CLAUDE.md
```

## Usage

```bash
# Start the server
uv run server.py

# In another terminal, send code
uv run client.py "print('hello')"
```

## Development

- Python 3.12+, managed by `uv`
- No external dependencies (stdlib only for the core)
- Socket path: `/tmp/repl-box.sock` (configurable via env var `REPL_BOX_SOCKET`)

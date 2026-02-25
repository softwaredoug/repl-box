# repl-box

[![CI](https://github.com/softwaredoug/repl-box/actions/workflows/ci.yml/badge.svg)](https://github.com/softwaredoug/repl-box/actions/workflows/ci.yml)

A sandboxed Python REPL server for agents. Runs as a separate process and communicates over a Unix domain socket, so agent-executed code is isolated from your application.

## WARNING: DO NOT USE WITH UNTRUSTED CODE

**repl-box executes arbitrary Python code with the full privileges of the user who launched it.** There is no sandboxing of what the code can do — it can read and delete files, make network requests, spawn processes, exfiltrate secrets, and anything else Python can do on your system.

"Sandboxed" in this project means *process isolation from your application*, not *security isolation from the system*. The server process shares your filesystem, network, environment variables, and user permissions.

**Only use repl-box in environments where you control or trust the code being sent to it.** Do not expose the socket to the network or to untrusted users. Do not run it as root. Do not run it on a machine with sensitive credentials unless you understand and accept the risks.

## Install

```bash
pip install git+https://github.com/softwaredoug/repl-box.git
```

## Usage

```python
import repl_box

with repl_box.start() as repl:
    repl.send("x = 6 * 7")
    result = repl.send("print(x)")
    print(result)  # {"stdout": "42\n", "stderr": "", "error": None}
```

### Preload variables from the calling process

```python
import pandas as pd
import repl_box

df = pd.read_csv("data.csv")

with repl_box.start(df=df) as repl:
    repl.send("print(df.shape)")
    repl.send("summary = df.describe()")
```

### Update variables without restarting

```python
import repl_box

with repl_box.start() as repl:
    repl.send("x = 1")
    repl.set(x=42)
    repl.send("print(x)")  # 42
```

### CLI

```bash
# Start the server
repl-box

# Send code from another terminal
repl-box-client "print('hello')"
echo "print(1 + 1)" | repl-box-client -
```

## Protocol

Newline-delimited JSON over a Unix domain socket (`/tmp/repl-box.sock` by default, override with `REPL_BOX_SOCKET`).

**Request:** `{"code": "print(1 + 1)"}`

**Response:** `{"stdout": "2\n", "stderr": "", "error": null}`

## Development

See `CONTRIBUTING.md` for the full dev workflow.

```bash
uv run pytest tests/ -v
```

# repl-box

[![CI](https://github.com/softwaredoug/repl-box/actions/workflows/ci.yml/badge.svg)](https://github.com/softwaredoug/repl-box/actions/workflows/ci.yml)

A sandboxed Python REPL server for agents. Runs as a separate process and communicates over a Unix domain socket, so agent-executed code is isolated from your application.

## Install

```bash
pip install git+https://github.com/softwaredoug/repl-box.git
```

## Usage

```python
import repl_box
from repl_box.client import send

# Start the server in the background
server = repl_box.start()

send("x = 6 * 7")
print(send("print(x)"))  # {"stdout": "42\n", "stderr": "", "error": None}

server.terminate()
```

### Preload variables from the calling process

```python
import pandas as pd
import repl_box
from repl_box.client import send

df = pd.read_csv("data.csv")

server = repl_box.start(df=df)

send("print(df.shape)")
send("summary = df.describe()")

server.terminate()
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

```bash
uv run pytest tests/ -v
```

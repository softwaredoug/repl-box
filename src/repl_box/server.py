#!/usr/bin/env python3
"""
repl-box server: a stateful Python REPL over a Unix domain socket.

Each connection sends one JSON request {"code": "..."} and receives
one JSON response {"stdout": "...", "stderr": "...", "error": "..."}.
State (variables, imports, definitions) persists across connections.
"""

import io
import json
import os
import signal
import socket
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout

SOCKET_PATH = os.environ.get("REPL_BOX_SOCKET", "/tmp/repl-box.sock")


def _format_input(code: str, n: int) -> str:
    lines = code.splitlines() or [""]
    header = f"In [{n}]: {lines[0]}\n"
    continuation = "".join(f"   ...: {line}\n" for line in lines[1:])
    return header + continuation


def execute(code: str, namespace: dict, counter: int) -> dict:
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    error = None
    out_repr = None

    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            try:
                result = eval(compile(code, "<repl>", "eval"), namespace)
                if result is not None:
                    out_repr = repr(result)
            except SyntaxError:
                exec(compile(code, "<repl>", "exec"), namespace)
    except Exception:
        error = traceback.format_exc().strip()

    stdout = _format_input(code, counter)
    raw = stdout_buf.getvalue()
    if raw:
        stdout += raw
        if not raw.endswith("\n"):
            stdout += "\n"
    if out_repr is not None:
        stdout += f"Out[{counter}]: {out_repr}\n"

    return {
        "stdout": stdout,
        "stderr": stderr_buf.getvalue(),
        "error": error,
    }


def handle(conn: socket.socket, namespace: dict, counter: list[int]) -> None:
    with conn:
        data = b""
        while b"\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk

        raw = data.split(b"\n")[0]
        if not raw:
            return

        try:
            request = json.loads(raw)
        except json.JSONDecodeError as e:
            response = {"stdout": "", "stderr": "", "error": f"Bad request: {e}"}
        else:
            if "set" in request:
                import base64
                import cloudpickle
                try:
                    updates = cloudpickle.loads(base64.b64decode(request["set"]))
                    namespace.update(updates)
                    response = {"stdout": "", "stderr": "", "error": None}
                except Exception:
                    import traceback as tb
                    response = {"stdout": "", "stderr": "", "error": tb.format_exc().strip()}
            elif "get" in request:
                import base64
                import cloudpickle
                import traceback as tb
                var_name = request["get"]
                if var_name not in namespace:
                    response = {"stdout": "", "stderr": "", "error": f"NameError: name '{var_name}' is not defined", "value": None}
                else:
                    try:
                        encoded = base64.b64encode(cloudpickle.dumps(namespace[var_name])).decode()
                        response = {"stdout": "", "stderr": "", "error": None, "value": encoded}
                    except Exception:
                        response = {"stdout": "", "stderr": "", "error": tb.format_exc().strip(), "value": None}
            elif "code" in request:
                response = execute(request["code"], namespace, counter[0])
                counter[0] += 1
            else:
                response = {"stdout": "", "stderr": "", "error": "Bad request: missing 'code', 'set', or 'get'"}

        conn.sendall(json.dumps(response).encode() + b"\n")


def load_init_namespace() -> dict:
    import cloudpickle

    init_path = os.environ.get("REPL_BOX_INIT")
    if not init_path:
        return {}
    try:
        with open(init_path, "rb") as f:
            namespace = cloudpickle.load(f)
    finally:
        os.unlink(init_path)
    return namespace


def serve() -> None:
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    namespace: dict = load_init_namespace()
    counter: list[int] = [1]

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    server.listen()

    def shutdown(sig, frame):
        print(f"\nShutting down ({SOCKET_PATH})", file=sys.stderr)
        server.close()
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"repl-box listening on {SOCKET_PATH}", file=sys.stderr)

    while True:
        try:
            conn, _ = server.accept()
        except OSError:
            break
        handle(conn, namespace, counter)


if __name__ == "__main__":
    serve()

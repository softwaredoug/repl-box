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


def execute(code: str, namespace: dict) -> dict:
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    error = None

    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exec(compile(code, "<repl>", "exec"), namespace)
    except Exception:
        error = traceback.format_exc().strip()

    return {
        "stdout": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
        "error": error,
    }


def handle(conn: socket.socket, namespace: dict) -> None:
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
            code = request["code"]
        except (json.JSONDecodeError, KeyError) as e:
            response = {"stdout": "", "stderr": "", "error": f"Bad request: {e}"}
        else:
            response = execute(code, namespace)

        conn.sendall(json.dumps(response).encode() + b"\n")


def load_init_namespace() -> dict:
    import pickle

    init_path = os.environ.get("REPL_BOX_INIT")
    if not init_path:
        return {}
    try:
        with open(init_path, "rb") as f:
            namespace = pickle.load(f)
    finally:
        os.unlink(init_path)
    return namespace


def serve() -> None:
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    namespace: dict = load_init_namespace()

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
        handle(conn, namespace)


if __name__ == "__main__":
    serve()

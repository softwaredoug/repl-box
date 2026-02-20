#!/usr/bin/env python3
"""
repl-box client: send Python code to the REPL server and print the result.

Usage:
    uv run client.py "print('hello')"
    uv run client.py "x = 42"
    echo "print(x)" | uv run client.py -
"""

import json
import os
import socket
import sys

SOCKET_PATH = os.environ.get("REPL_BOX_SOCKET", "/tmp/repl-box.sock")


def send(code: str) -> dict:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(SOCKET_PATH)
    with sock, sock.makefile("rb") as f:
        sock.sendall(json.dumps({"code": code}).encode() + b"\n")
        raw = f.readline()
    return json.loads(raw)


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: client.py <code | ->", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "-":
        code = sys.stdin.read()
    else:
        code = sys.argv[1]

    result = send(code)

    if result["stdout"]:
        print(result["stdout"], end="")
    if result["stderr"]:
        print(result["stderr"], end="", file=sys.stderr)
    if result["error"]:
        print(result["error"], file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

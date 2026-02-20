import json
import os
import socket

import pytest

from repl_box import start

SOCKET_PATH = "/tmp/repl-box-test.sock"


def send(code: str) -> dict:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(SOCKET_PATH)
    with sock, sock.makefile("rb") as f:
        sock.sendall(json.dumps({"code": code}).encode() + b"\n")
        raw = f.readline()
    return json.loads(raw)


@pytest.fixture(scope="module")
def server():
    proc = start(socket_path=SOCKET_PATH)
    yield proc
    proc.terminate()
    proc.wait()
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)


def test_simple_expression(server):
    result = send("print(1 + 1)")
    assert result["stdout"] == "2\n"
    assert result["stderr"] == ""
    assert result["error"] is None

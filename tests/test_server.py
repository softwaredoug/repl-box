import json
import os
import socket
import subprocess
import sys
import time

import pytest

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
    env = os.environ.copy()
    env["REPL_BOX_SOCKET"] = SOCKET_PATH

    proc = subprocess.Popen(
        [sys.executable, "-m", "repl_box.server"],
        env=env,
        stderr=subprocess.PIPE,
    )

    # Wait for the socket to appear
    deadline = time.monotonic() + 5.0
    while not os.path.exists(SOCKET_PATH):
        if time.monotonic() > deadline:
            proc.kill()
            raise RuntimeError("server did not start in time")
        time.sleep(0.05)

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

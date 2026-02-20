import os

import pytest

import repl_box
from repl_box.client import send

SOCKET_PATH = "/tmp/repl-box-test.sock"


@pytest.fixture(scope="module")
def server():
    proc = repl_box.start(socket_path=SOCKET_PATH)
    yield proc
    proc.terminate()
    proc.wait()
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)


def test_simple_expression(server):
    result = send("print(1 + 1)", socket_path=SOCKET_PATH)
    assert result["stdout"] == "2\n"
    assert result["stderr"] == ""
    assert result["error"] is None


def test_preloaded_variables():
    numbers = [1, 2, 3]
    greeting = "hello"

    proc = repl_box.start(
        socket_path="/tmp/repl-box-preload-test.sock",
        numbers=numbers,
        greeting=greeting,
    )
    try:
        result = send("print(greeting, sum(numbers))", socket_path="/tmp/repl-box-preload-test.sock")
        assert result["stdout"] == "hello 6\n"
        assert result["error"] is None
    finally:
        proc.terminate()
        proc.wait()
        if os.path.exists("/tmp/repl-box-preload-test.sock"):
            os.unlink("/tmp/repl-box-preload-test.sock")

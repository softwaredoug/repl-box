import os

import pandas as pd
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
    assert "In [" in result["stdout"]
    assert "print(1 + 1)" in result["stdout"]
    assert "\n2\n" in result["stdout"]
    assert "Out[" not in result["stdout"]   # print output, not an expression
    assert result["error"] is None


def test_expression_repr(server):
    send("x = [1, 2]", socket_path=SOCKET_PATH)
    result = send("x", socket_path=SOCKET_PATH)
    assert "Out[" in result["stdout"]
    assert "[1, 2]" in result["stdout"]
    assert result["error"] is None


def test_dataframe_interactions():
    df = pd.DataFrame({
        "name": ["alice", "bob", "carol"],
        "score": [85, 92, 78],
    })

    proc = repl_box.start(socket_path="/tmp/repl-box-df-test.sock", df=df)
    try:
        sock = "/tmp/repl-box-df-test.sock"

        # inspect shape
        result = send("print(df.shape)", socket_path=sock)
        assert "(3, 2)" in result["stdout"]
        assert result["error"] is None

        # filter and assign — state persists
        result = send("high = df[df['score'] >= 85]", socket_path=sock)
        assert result["error"] is None

        # use the result of the previous call
        result = send("print(list(high['name']))", socket_path=sock)
        assert "['alice', 'bob']" in result["stdout"]
        assert result["error"] is None

        # mutate the original df
        result = send("df['grade'] = df['score'].apply(lambda s: 'A' if s >= 85 else 'B')", socket_path=sock)
        assert result["error"] is None

        result = send("print(list(df['grade']))", socket_path=sock)
        assert "['A', 'A', 'B']" in result["stdout"]
        assert result["error"] is None

        # expression output — df itself should appear as Out[N]:
        result = send("df", socket_path=sock)
        assert "Out[" in result["stdout"]
        assert "alice" in result["stdout"]
        assert "score" in result["stdout"]
        assert result["error"] is None
    finally:
        proc.terminate()
        proc.wait()
        if os.path.exists("/tmp/repl-box-df-test.sock"):
            os.unlink("/tmp/repl-box-df-test.sock")


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
        assert "hello 6" in result["stdout"]
        assert result["error"] is None
    finally:
        proc.terminate()
        proc.wait()
        if os.path.exists("/tmp/repl-box-preload-test.sock"):
            os.unlink("/tmp/repl-box-preload-test.sock")

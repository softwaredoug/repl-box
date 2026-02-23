import os

import pandas as pd
import pytest

import repl_box

SOCKET_PATH = "/tmp/repl-box-test.sock"


@pytest.fixture(scope="module")
def repl():
    with repl_box.start(socket_path=SOCKET_PATH) as repl:
        yield repl


def test_simple_expression(repl):
    result = repl.send("print(1 + 1)")
    assert "In [" in result["stdout"]
    assert "print(1 + 1)" in result["stdout"]
    assert "\n2\n" in result["stdout"]
    assert "Out[" not in result["stdout"]   # print output, not an expression
    assert result["error"] is None


def test_expression_repr(repl):
    repl.send("x = [1, 2]")
    result = repl.send("x")
    assert "Out[" in result["stdout"]
    assert "[1, 2]" in result["stdout"]
    assert result["error"] is None


def test_dataframe_interactions():
    df = pd.DataFrame({
        "name": ["alice", "bob", "carol"],
        "score": [85, 92, 78],
    })

    with repl_box.start(socket_path="/tmp/repl-box-df-test.sock", df=df) as repl:
        # inspect shape
        result = repl.send("print(df.shape)")
        assert "(3, 2)" in result["stdout"]
        assert result["error"] is None

        # filter and assign — state persists
        result = repl.send("high = df[df['score'] >= 85]")
        assert result["error"] is None

        # use the result of the previous call
        result = repl.send("print(list(high['name']))")
        assert "['alice', 'bob']" in result["stdout"]
        assert result["error"] is None

        # mutate the original df
        repl.send("df['grade'] = df['score'].apply(lambda s: 'A' if s >= 85 else 'B')")

        result = repl.send("print(list(df['grade']))")
        assert "['A', 'A', 'B']" in result["stdout"]
        assert result["error"] is None

        # expression output — df itself should appear as Out[N]:
        result = repl.send("df")
        assert "Out[" in result["stdout"]
        assert "alice" in result["stdout"]
        assert "score" in result["stdout"]
        assert result["error"] is None


def test_preloaded_variables():
    numbers = [1, 2, 3]
    greeting = "hello"

    with repl_box.start(
        socket_path="/tmp/repl-box-preload-test.sock",
        numbers=numbers,
        greeting=greeting,
    ) as repl:
        result = repl.send("print(greeting, sum(numbers))")
        assert "hello 6" in result["stdout"]
        assert result["error"] is None


def test_set_updates_namespace():
    with repl_box.start(socket_path="/tmp/repl-box-set-test.sock", x=1) as repl:
        assert "1" in repl.send("x")["stdout"]

        repl.set(x=99)
        result = repl.send("x")
        assert "99" in result["stdout"]
        assert result["error"] is None

        # set multiple at once
        repl.set(a=10, b=20)
        result = repl.send("a + b")
        assert "30" in result["stdout"]
        assert result["error"] is None


def test_repl_list():
    with repl_box.start(socket_path="/tmp/repl-box-list-test.sock") as repl:
        history = repl.list("history")

        history.append("user: hello")
        history.append("assistant: hi")
        result = repl.send("len(history)")
        assert "2" in result["stdout"]

        history.extend(["user: bye", "assistant: goodbye"])
        result = repl.send("history[-1]")
        assert "goodbye" in result["stdout"]

        history[0] = "user: hey"
        result = repl.send("history[0]")
        assert "hey" in result["stdout"]

        history.pop()
        result = repl.send("len(history)")
        assert "3" in result["stdout"]

        assert history == ["user: hey", "assistant: hi", "user: bye"]
        assert len(history) == 3
        assert "assistant: hi" in history

        import json
        assert json.dumps(history) == '["user: hey", "assistant: hi", "user: bye"]'


def test_restart_with_new_variables():
    """Second start() on the same socket path must use the new namespace, not the old server."""
    sock = "/tmp/repl-box-restart-test.sock"

    with repl_box.start(socket_path=sock, x=1) as repl:
        assert repl.send("x")["error"] is None

    # Start a fresh server on the same path with a different variable
    with repl_box.start(socket_path=sock, x=99) as repl:
        result = repl.send("x")
        assert "99" in result["stdout"]
        assert result["error"] is None

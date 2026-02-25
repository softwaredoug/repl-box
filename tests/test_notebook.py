"""Tests for notebook global cleaning.

Uses IPython.core.interactiveshell.InteractiveShell to simulate the IPython
environment without a full Jupyter kernel.

Key finding: cloudpickle only serializes globals *referenced* by a function's
bytecode. In the IPython shell, get_ipython / exit / quit each transitively
hold a sqlite3.Connection that cloudpickle cannot serialize. So a function
that references get_ipython will fail; one that doesn't will succeed — even
though both share the same notebook globals dict.

In real Jupyter/Colab (with ipykernel), ZMQ sockets appear in the same way:
any function that references a global touching the kernel will fail.
clean_for_notebook strips those globals so the function can be pickled safely.
"""
import cloudpickle
import pytest

import repl_box
from repl_box._notebook import clean_for_notebook, _is_notebook_global

from IPython.core.interactiveshell import InteractiveShell


@pytest.fixture(scope="module")
def shell():
    return InteractiveShell.instance()


# ---------------------------------------------------------------------------
# _is_notebook_global — unit tests
# ---------------------------------------------------------------------------

def test_detects_ipython_injected_names():
    assert _is_notebook_global('get_ipython', lambda: None)
    assert _is_notebook_global('In', [])
    assert _is_notebook_global('Out', {})
    assert _is_notebook_global('_i', '')
    assert _is_notebook_global('_i42', '')
    assert _is_notebook_global('display', None)


def test_detects_zmq_type():
    class FakeZMQSocket:
        pass
    FakeZMQSocket.__module__ = 'zmq.backend.cython._zmq'
    assert _is_notebook_global('_socket', FakeZMQSocket())


def test_passes_normal_globals():
    assert not _is_notebook_global('patent_search_cache', {})
    assert not _is_notebook_global('MY_API_KEY', 'abc123')
    assert not _is_notebook_global('Patent', object)


# ---------------------------------------------------------------------------
# clean_for_notebook
# ---------------------------------------------------------------------------

def test_passthrough_outside_notebook():
    """Outside a notebook, the function is returned unchanged."""
    def my_fn(x):
        return x * 2

    cleaned = clean_for_notebook(my_fn)
    assert cleaned is my_fn


def test_strips_ipython_globals(shell):
    """Named IPython globals (get_ipython, In, Out, etc.) are removed."""
    shell.run_cell("def simple(x):\n    return x + 1")
    fn = shell.user_ns['simple']

    assert 'get_ipython' in fn.__globals__

    cleaned = clean_for_notebook(fn)
    assert 'get_ipython' not in cleaned.__globals__
    assert 'In' not in cleaned.__globals__
    assert 'Out' not in cleaned.__globals__


def test_ipython_globals_unpicklable(shell):
    """A function referencing get_ipython fails to pickle (sqlite3.Connection
    is in its object graph). This is analogous to ZMQ sockets in Jupyter."""
    shell.run_cell("def fn_refs_ipython(x):\n    ip = get_ipython()\n    return x")
    fn = shell.user_ns['fn_refs_ipython']

    with pytest.raises(Exception, match="sqlite3"):
        cloudpickle.dumps(fn)


def test_clean_for_notebook_fixes_unpicklable_globals(shell):
    """After cleaning, pickling succeeds even if the function transitively
    referenced an unpicklable global (e.g. get_ipython → sqlite3.Connection).

    Note: if the function *calls* get_ipython at runtime it will still raise
    NameError after cleaning — that global is gone. In practice, notebook
    functions passed to repl-box only share globals with get_ipython; they
    don't call it directly.
    """
    shell.run_cell("def fn_to_clean(x):\n    ip = get_ipython()\n    return x * 3")
    fn = shell.user_ns['fn_to_clean']

    with pytest.raises(Exception):
        cloudpickle.dumps(fn)

    cleaned = clean_for_notebook(fn)
    data = cloudpickle.dumps(cleaned)
    assert data is not None  # pickling now succeeds


def test_function_works_after_cleaning(shell):
    """A clean function with no bad globals still runs correctly."""
    shell.run_cell("def greet(name):\n    return f'hello {name}'")
    fn = shell.user_ns['greet']

    cleaned = clean_for_notebook(fn)
    data = cloudpickle.dumps(cleaned)
    restored = cloudpickle.loads(data)
    assert restored('world') == 'hello world'


# ---------------------------------------------------------------------------
# End-to-end: repl_box.start() and repl.set() with notebook-style functions
# ---------------------------------------------------------------------------

def test_start_with_notebook_function(shell):
    """start() succeeds for a function defined in an IPython shell."""
    shell.run_cell("def score(x):\n    return x * 10")
    fn = shell.user_ns['score']

    with repl_box.start(socket_path="/tmp/repl-box-nb-start-test.sock", score=fn) as repl:
        result = repl.send("score(5)")
        assert "50" in result["stdout"]
        assert result["error"] is None


def test_set_with_notebook_function(shell):
    """repl.set() succeeds for a function defined in an IPython shell."""
    shell.run_cell("def double(x):\n    return x * 2")
    fn = shell.user_ns['double']

    with repl_box.start(socket_path="/tmp/repl-box-nb-set-test.sock") as repl:
        repl.set(double=fn)
        result = repl.send("double(21)")
        assert "42" in result["stdout"]
        assert result["error"] is None


def test_cross_function_reference(shell):
    """A notebook function that calls another notebook function works after cleaning."""
    shell.run_cell(
        "def helper(x):\n    return x * 2\n"
        "def main_fn(x):\n    return helper(x) + 1\n"
    )
    fn = shell.user_ns['main_fn']
    cleaned = clean_for_notebook(fn)
    restored = cloudpickle.loads(cloudpickle.dumps(cleaned))
    assert restored(5) == 11   # helper(5)=10, +1=11


def test_start_cross_function(shell):
    """End-to-end: notebook function calling a helper works in the server."""
    shell.run_cell(
        "def _double(x):\n    return x * 2\n"
        "def compute(x):\n    return _double(x) + 3\n"
    )
    fn = shell.user_ns['compute']
    with repl_box.start(socket_path="/tmp/repl-box-nb-cross-test.sock", compute=fn) as repl:
        result = repl.send("compute(7)")
        assert "17" in result["stdout"]   # _double(7)=14, +3=17
        assert result["error"] is None


def test_notebook_function_with_pydantic(shell):
    """Mirrors the patent_search pattern: notebook function returning a pydantic model.

    Both the model class and the function are defined in the IPython shell so
    Patent is naturally in the shared globals — no manual injection needed.
    """
    shell.run_cell(
        "from pydantic import BaseModel\n"
        "class Patent(BaseModel):\n"
        "    title: str\n"
        "    inventor: str\n"
        "def find_patent(keywords):\n"
        "    return Patent(title=f'Patent on {keywords}', inventor='Alice')\n"
    )
    fn = shell.user_ns['find_patent']

    with repl_box.start(socket_path="/tmp/repl-box-nb-pydantic-test.sock",
                        find_patent=fn) as repl:
        r = repl.send("result = find_patent('EV battery')")
        assert r["error"] is None, f"find_patent failed: {r['error']}"
        assert "Alice" in repl.send("result.inventor")["stdout"]
        assert "EV battery" in repl.send("result.title")["stdout"]

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


def test_set_function():
    """cloudpickle should serialize locally defined functions."""
    def score(x):
        return x * 2 + 1

    with repl_box.start(socket_path="/tmp/repl-box-fn-test.sock") as repl:
        repl.set(score=score)
        result = repl.send("score(10)")
        assert "21" in result["stdout"]
        assert result["error"] is None


def test_preload_function():
    """Functions passed to start() should be available in the namespace."""
    def greet(name):
        return f"hello, {name}!"

    with repl_box.start(socket_path="/tmp/repl-box-fn-preload-test.sock", greet=greet) as repl:
        result = repl.send("greet('world')")
        assert "hello, world!" in result["stdout"]
        assert result["error"] is None


def test_function_takes_pydantic_arg():
    """A function that accepts a pydantic model can be passed to the repl and called there."""
    from pydantic import BaseModel

    class SearchQuery(BaseModel):
        keywords: str
        max_results: int = 10

    def run_search(query: SearchQuery) -> str:
        return f"searched for '{query.keywords}', limit {query.max_results}"

    with repl_box.start(socket_path="/tmp/repl-box-fn-pydantic-arg-test.sock",
                        run_search=run_search,
                        SearchQuery=SearchQuery) as repl:
        result = repl.send("run_search(SearchQuery(keywords='electric car battery', max_results=5))")
        assert "electric car battery" in result["stdout"]
        assert "5" in result["stdout"]
        assert result["error"] is None


def test_function_returns_pydantic():
    """A function that returns a pydantic model — repl can access its fields."""
    from pydantic import BaseModel

    class SearchResult(BaseModel):
        title: str
        inventor: str
        score: float

    def top_result(keywords: str) -> SearchResult:
        return SearchResult(title=f"Patent on {keywords}", inventor="Jane Doe", score=0.95)

    with repl_box.start(socket_path="/tmp/repl-box-fn-pydantic-ret-test.sock",
                        top_result=top_result) as repl:
        repl.send("result = top_result('battery')")
        assert repl.send("result.inventor")["stdout"].find("Jane Doe") != -1
        assert repl.send("result.score")["stdout"].find("0.95") != -1
        assert repl.send("result.title")["stdout"].find("battery") != -1


def test_function_with_pydantic_cache():
    """Mirrors the patent_search pattern: function closes over a dict cache and pydantic models."""
    from pydantic import BaseModel, Field

    class Patent(BaseModel):
        title: str
        inventor: str

    class PatentResults(BaseModel):
        query: str
        results: list[Patent]

    cache = {}

    def patent_search(keywords: str) -> PatentResults:
        if keywords not in cache:
            cache[keywords] = PatentResults(
                query=keywords,
                results=[Patent(title=f"Patent on {keywords}", inventor="Alice")]
            )
        return cache[keywords]

    with repl_box.start(socket_path="/tmp/repl-box-patent-search-test.sock",
                        patent_search=patent_search) as repl:
        repl.send("r = patent_search('EV battery')")
        assert repl.send("r.query")["stdout"].find("EV battery") != -1
        assert repl.send("r.results[0].inventor")["stdout"].find("Alice") != -1
        assert repl.send("r.results[0].title")["stdout"].find("EV battery") != -1

        # second call hits the cache
        repl.send("r2 = patent_search('EV battery')")
        assert repl.send("r2.results[0].title")["stdout"].find("EV battery") != -1
        assert repl.send("r is r2")["stdout"].find("True") != -1


def test_get_simple_value():
    with repl_box.start(socket_path="/tmp/repl-box-get-simple-test.sock") as repl:
        repl.send("x = 42")
        assert repl.get("x") == 42


def test_get_after_mutation():
    items = [1, 2, 3]
    with repl_box.start(socket_path="/tmp/repl-box-get-mutation-test.sock", items=items) as repl:
        repl.send("items.append(4)")
        result = repl.get("items")
        assert result == [1, 2, 3, 4]


def test_get_dataframe_mutation():
    df = pd.DataFrame({"a": [1, 2, 3]})
    with repl_box.start(socket_path="/tmp/repl-box-get-df-test.sock", df=df) as repl:
        repl.send("df['b'] = df['a'] * 2")
        result = repl.get("df")
        assert list(result["b"]) == [2, 4, 6]


def test_get_function_result():
    def square(x):
        return x * x

    with repl_box.start(socket_path="/tmp/repl-box-get-fn-result-test.sock", square=square) as repl:
        repl.send("result = square(7)")
        assert repl.get("result") == 49


def test_get_undefined_raises():
    with repl_box.start(socket_path="/tmp/repl-box-get-undef-test.sock") as repl:
        with pytest.raises(NameError):
            repl.get("y")


def test_get_pydantic_model():
    from pydantic import BaseModel

    class Point(BaseModel):
        x: float
        y: float

    with repl_box.start(socket_path="/tmp/repl-box-get-pydantic-test.sock", Point=Point) as repl:
        repl.send("p = Point(x=1.5, y=2.5)")
        result = repl.get("p")
        assert result.x == 1.5
        assert result.y == 2.5


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

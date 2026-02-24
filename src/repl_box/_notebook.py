"""Utilities for cleaning notebook globals before cloudpickle serialization.

In Jupyter/Colab, every function defined in a cell has __globals__ pointing
at the kernel namespace, which contains ZMQ socket references that cloudpickle
cannot serialize. This module detects that environment and strips those globals.
"""
import types

_IPYTHON_INJECTED = frozenset({
    'get_ipython', 'display',
    'exit', 'quit',
    'In', 'Out',
    '_', '__', '___',
    '_i', '_ii', '_iii',
    '_ih', '_oh', '_dh',
})


def _is_notebook_global(k: str, v) -> bool:
    """Return True if this global was injected by IPython/Jupyter."""
    if k in _IPYTHON_INJECTED:
        return True
    if k.startswith('_i') and k[2:].isdigit():   # _i1, _i2, ...
        return True
    module = getattr(type(v), '__module__', '') or ''
    return module.startswith(('zmq.', 'ipykernel.', 'IPython.'))


def clean_for_notebook(fn):
    """Return a copy of fn with unpicklable notebook globals stripped.

    Outside a notebook (no get_ipython in globals), fn is returned unchanged.

    Strategy: named denylist for known IPython/ZMQ types (fast), then
    try-except cloudpickle for anything else that slips through (robust).
    This catches sqlite3.Connection (IPython history DB), ZMQ sockets, etc.
    """
    import cloudpickle as _cp

    if not callable(fn) or not hasattr(fn, '__globals__'):
        return fn
    if 'get_ipython' not in fn.__globals__:
        return fn
    clean = {}
    for k, v in fn.__globals__.items():
        if _is_notebook_global(k, v):
            continue
        try:
            _cp.dumps(v)
            clean[k] = v
        except Exception:
            pass  # drop anything cloudpickle can't handle
    return types.FunctionType(
        fn.__code__,
        clean,
        fn.__name__,
        fn.__defaults__,
        fn.__closure__,
    )


def prepare_variables(variables: dict) -> dict:
    """Apply notebook global cleaning to any callables in a variables dict."""
    return {k: clean_for_notebook(v) for k, v in variables.items()}

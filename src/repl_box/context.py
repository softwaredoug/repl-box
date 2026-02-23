from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repl_box import Repl


class Context(list):
    """A list that syncs its contents to a named variable in a Repl server.

    Subclasses list so it is JSON-serializable out of the box. Pydantic models
    (e.g. OpenAI response objects) are coerced to plain dicts via model_dump()
    at insertion time — they carry unpicklable OS resources in their object graphs
    and plain dicts are what the OpenAI API accepts back anyway.

        with repl_box.start() as repl:
            inputs = repl.context("inputs")
            inputs.append({"role": "user", "content": "hello"})
            resp = client.responses.create(...)
            inputs += resp.output  # ResponseOutputItem objects coerced automatically
            client.responses.create(input=inputs, ...)
    """

    def __init__(self, repl: "Repl", name: str, initial=None):
        super().__init__(initial or [])
        self._repl = repl
        self._name = name
        self._sync()

    @staticmethod
    def _coerce(item):
        """Coerce pydantic models to plain dicts via model_dump(exclude_none=True).

        Excluding None fields is necessary because OpenAI rejects unknown/null
        parameters (e.g. status=None on a reasoning item) when items are passed
        back as input to a subsequent API call.
        """
        if hasattr(item, "model_dump"):
            return item.model_dump(exclude_none=True)
        return item

    def _sync(self):
        self._repl.set(**{self._name: list(self)})

    def append(self, item):
        super().append(self._coerce(item))
        self._sync()

    def extend(self, items):
        super().extend(self._coerce(i) for i in items)
        self._sync()

    def insert(self, index, item):
        super().insert(index, self._coerce(item))
        self._sync()

    def remove(self, item):
        super().remove(item)
        self._sync()

    def pop(self, index=-1):
        item = super().pop(index)
        self._sync()
        return item

    def clear(self):
        super().clear()
        self._sync()

    def sort(self, *, key=None, reverse=False):
        super().sort(key=key, reverse=reverse)
        self._sync()

    def reverse(self):
        super().reverse()
        self._sync()

    def __setitem__(self, index, value):
        super().__setitem__(index, self._coerce(value))
        self._sync()

    def __delitem__(self, index):
        super().__delitem__(index)
        self._sync()

    def __iadd__(self, other):
        super().extend(self._coerce(i) for i in other)
        self._sync()
        return self

    def __imul__(self, n):
        super().__imul__(n)
        self._sync()
        return self

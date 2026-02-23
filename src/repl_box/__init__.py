import base64
import json
import os
import pickle
import socket
import subprocess
import sys
import tempfile
import time


class Repl:
    def __init__(self, proc: subprocess.Popen, socket_path: str):
        self._proc = proc
        self._socket_path = socket_path

    def _request(self, payload: dict) -> dict:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self._socket_path)
        with sock, sock.makefile("rb") as f:
            sock.sendall(json.dumps(payload).encode() + b"\n")
            raw = f.readline()
        return json.loads(raw)

    def send(self, code: str) -> dict:
        return self._request({"code": code})

    def set(self, **variables) -> None:
        payload = base64.b64encode(pickle.dumps(variables)).decode()
        result = self._request({"set": payload})
        if result.get("error"):
            raise RuntimeError(result["error"])

    def list(self, name: str, initial=None) -> "ReplList":
        """Create a ReplList bound to this server under the given variable name."""
        return ReplList(self, name, initial)

    def close(self) -> None:
        self._proc.terminate()
        self._proc.wait()
        if os.path.exists(self._socket_path):
            os.unlink(self._socket_path)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ReplList(list):
    """A list that syncs its contents to a named variable in a Repl server.

    Subclasses list so it is JSON-serializable out of the box.

        repl = repl_box.start()
        history = repl.list("history")
        history.append({"role": "user", "content": "hello"})
        client.chat.completions.create(messages=history, ...)
    """

    def __init__(self, repl: "Repl", name: str, initial=None):
        super().__init__(initial or [])
        self._repl = repl
        self._name = name
        self._sync()

    def _sync(self):
        self._repl.set(**{self._name: list(self)})

    def append(self, item):
        super().append(item)
        self._sync()

    def extend(self, items):
        super().extend(items)
        self._sync()

    def insert(self, index, item):
        super().insert(index, item)
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
        super().__setitem__(index, value)
        self._sync()

    def __delitem__(self, index):
        super().__delitem__(index)
        self._sync()

    def __iadd__(self, other):
        super().__iadd__(other)
        self._sync()
        return self

    def __imul__(self, n):
        super().__imul__(n)
        self._sync()
        return self


def start(
    socket_path: str | None = None,
    timeout: float = 5.0,
    **variables,
) -> Repl:
    """Start the repl-box server in the background. Returns a Repl instance.

    Any keyword arguments are pickled and pre-loaded into the server's namespace:
        repl = repl_box.start(df=my_dataframe, model=my_model)
        repl.send("print(df.shape)")
    """
    env = os.environ.copy()
    resolved = socket_path or env.get("REPL_BOX_SOCKET", "/tmp/repl-box.sock")

    if socket_path:
        env["REPL_BOX_SOCKET"] = socket_path

    if variables:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pkl")
        pickle.dump(variables, tmp)
        tmp.close()
        env["REPL_BOX_INIT"] = tmp.name

    # Remove any leftover socket so the wait loop below always waits for
    # the new server rather than returning immediately against an old one.
    if os.path.exists(resolved):
        os.unlink(resolved)

    proc = subprocess.Popen(
        [sys.executable, "-m", "repl_box.server"],
        env=env,
        stderr=subprocess.PIPE,
    )

    deadline = time.monotonic() + timeout
    while not os.path.exists(resolved):
        if time.monotonic() > deadline:
            proc.kill()
            raise RuntimeError(f"repl-box server did not start within {timeout}s")
        time.sleep(0.05)

    return Repl(proc, resolved)

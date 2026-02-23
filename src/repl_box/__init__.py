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

    def close(self) -> None:
        self._proc.terminate()
        self._proc.wait()
        if os.path.exists(self._socket_path):
            os.unlink(self._socket_path)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ReplList:
    """A list that syncs its contents to a named variable in a Repl server.

    Useful for letting an LLM accumulate context via normal list operations
    while keeping the server's namespace up to date automatically.

        repl = repl_box.start()
        history = ReplList(repl, "history")
        history.append("user: hello")   # repl sees history == ["user: hello"]
    """

    def __init__(self, repl: "Repl", name: str, initial=None):
        self._repl = repl
        self._name = name
        self._data = list(initial) if initial is not None else []
        self._sync()

    def _sync(self):
        self._repl.set(**{self._name: self._data})

    # --- mutating methods ---

    def append(self, item):
        self._data.append(item)
        self._sync()

    def extend(self, items):
        self._data.extend(items)
        self._sync()

    def insert(self, index, item):
        self._data.insert(index, item)
        self._sync()

    def remove(self, item):
        self._data.remove(item)
        self._sync()

    def pop(self, index=-1):
        item = self._data.pop(index)
        self._sync()
        return item

    def clear(self):
        self._data.clear()
        self._sync()

    def sort(self, *, key=None, reverse=False):
        self._data.sort(key=key, reverse=reverse)
        self._sync()

    def reverse(self):
        self._data.reverse()
        self._sync()

    def __setitem__(self, index, value):
        self._data[index] = value
        self._sync()

    def __delitem__(self, index):
        del self._data[index]
        self._sync()

    def __iadd__(self, other):
        self._data += list(other)
        self._sync()
        return self

    def __imul__(self, n):
        self._data *= n
        self._sync()
        return self

    # --- read-only methods ---

    def __getitem__(self, index):
        return self._data[index]

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def __contains__(self, item):
        return item in self._data

    def __eq__(self, other):
        if isinstance(other, ReplList):
            return self._data == other._data
        return self._data == other

    def __repr__(self):
        return repr(self._data)

    def index(self, item, *args):
        return self._data.index(item, *args)

    def count(self, item):
        return self._data.count(item)

    def copy(self):
        return self._data.copy()


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

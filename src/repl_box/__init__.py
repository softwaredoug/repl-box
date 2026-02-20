import os
import pickle
import subprocess
import sys
import tempfile
import time


def start(
    socket_path: str | None = None,
    timeout: float = 5.0,
    **variables,
) -> subprocess.Popen:
    """Start the repl-box server in the background. Returns the process handle.

    Any keyword arguments are pickled and pre-loaded into the server's namespace:
        server = repl_box.start(df=my_dataframe, model=my_model)
    """
    env = os.environ.copy()
    if socket_path:
        env["REPL_BOX_SOCKET"] = socket_path

    resolved = socket_path or env.get("REPL_BOX_SOCKET", "/tmp/repl-box.sock")

    if variables:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pkl")
        pickle.dump(variables, tmp)
        tmp.close()
        env["REPL_BOX_INIT"] = tmp.name

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

    return proc

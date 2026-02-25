"""Execute VS Code-style cell files in a real Jupyter kernel."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

import pytest


try:
    from jupyter_client import KernelManager  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency
    KernelManager = None


CELL_DIR = Path(__file__).parent / "resources" / "jupyter_cells"


@dataclass
class Cell:
    source: str
    expect_text: list[str]
    expect_regex: list[str]
    expect_err: list[str]


def _parse_cell_files() -> list[Cell]:
    cells: list[Cell] = []
    if not CELL_DIR.exists():
        return cells

    for path in sorted(CELL_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        current_lines: list[str] = []
        expect_text: list[str] = []
        expect_regex: list[str] = []
        expect_err: list[str] = []

        def flush() -> None:
            nonlocal current_lines, expect_text, expect_regex, expect_err
            if not current_lines:
                return
            source = "".join(current_lines).strip("\n")
            if source:
                cells.append(
                    Cell(
                        source=source,
                        expect_text=expect_text,
                        expect_regex=expect_regex,
                        expect_err=expect_err,
                    )
                )
            current_lines = []
            expect_text = []
            expect_regex = []
            expect_err = []

        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("# %%"):
                flush()
                header = stripped[len("# %%") :].strip()
                if header.startswith("EXPECT:"):
                    expect_text.append(header[len("EXPECT:") :].strip())
                elif header.startswith("EXPECT-RE:"):
                    expect_regex.append(header[len("EXPECT-RE:") :].strip())
                elif header.startswith("EXPECT-ERR:"):
                    expect_err.append(header[len("EXPECT-ERR:") :].strip())
                continue
            current_lines.append(line)

        flush()

    return cells


def _capture_stream(msgs: list[dict], name: str) -> str:
    return "".join(
        msg.get("content", {}).get("text", "")
        for msg in msgs
        if msg.get("msg_type") == "stream"
        and msg.get("content", {}).get("name") == name
    )


def _capture_execute_result(msgs: list[dict]) -> str:
    output = []
    for msg in msgs:
        if msg.get("msg_type") != "execute_result":
            continue
        data = msg.get("content", {}).get("data", {})
        if "text/plain" in data:
            output.append(data["text/plain"])
    return "".join(output)


def _collect_iopub_msgs(kc, msg_id: str, timeout: float) -> list[dict]:
    msgs: list[dict] = []
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("timed out waiting for iopub messages")
        msg = kc.get_iopub_msg(timeout=remaining)
        if msg.get("parent_header", {}).get("msg_id") != msg_id:
            continue
        msgs.append(msg)
        if (
            msg.get("msg_type") == "status"
            and msg.get("content", {}).get("execution_state") == "idle"
        ):
            return msgs


def _wait_for_execute_reply(kc, msg_id: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("timed out waiting for execute_reply")
        msg = kc.get_shell_msg(timeout=remaining)
        if msg.get("parent_header", {}).get("msg_id") == msg_id:
            return


@pytest.mark.integration
def test_jupyter_cell_files():
    if KernelManager is None:
        pytest.skip("jupyter_client not installed")

    cells = _parse_cell_files()
    if not cells:
        pytest.skip("no jupyter cell files found")

    km = KernelManager()
    kc = None
    km.start_kernel()
    try:
        kc = km.client()
        kc.start_channels()
        kc.wait_for_ready(timeout=30)

        for index, cell in enumerate(cells, start=1):
            msg_id = kc.execute(cell.source)
            msgs = _collect_iopub_msgs(kc, msg_id, timeout=30)
            _wait_for_execute_reply(kc, msg_id, timeout=30)
            stdout = _capture_stream(msgs, "stdout")
            stderr = _capture_stream(msgs, "stderr")
            execute_result = _capture_execute_result(msgs)

            error = None
            for msg in msgs:
                if msg.get("msg_type") == "error":
                    error = "\n".join(msg.get("content", {}).get("traceback", []))
                    break

            if cell.expect_err:
                assert error is not None, f"cell {index} expected error"
                for expected in cell.expect_err:
                    assert expected in error, (
                        f"cell {index} missing expected error: {expected}"
                    )
                continue

            assert error is None, f"cell {index} raised error: {error}"

            combined = "".join([stdout, stderr, execute_result])
            for expected in cell.expect_text:
                assert expected in combined, (
                    f"cell {index} missing expected text: {expected}"
                )
            for pattern in cell.expect_regex:
                assert re.search(pattern, combined), (
                    f"cell {index} missing expected pattern: {pattern}"
                )
    finally:
        if kc is not None:
            try:
                kc.stop_channels()
            finally:
                km.shutdown_kernel(now=True)
        else:
            km.shutdown_kernel(now=True)

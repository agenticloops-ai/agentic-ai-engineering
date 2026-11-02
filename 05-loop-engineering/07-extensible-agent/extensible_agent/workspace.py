"""Layer: workspace. Read-only file tools and sandboxed execution over one project folder."""

import asyncio
import contextlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from extensible_agent.tools import Tool, ToolOutput

POLL_SECONDS = 0.02
RSS_SAMPLE_SECONDS = 0.1
MAX_READ_CHARS = 8_000

# Applies the limits inside the child, then replaces itself with the untrusted program
BOOTSTRAP = """
import os, resource, sys

def limit(name, value):
    try:
        resource.setrlimit(getattr(resource, name), (value, value))
    except (ValueError, OSError):
        pass  # macOS rejects RLIMIT_AS and RLIMIT_DATA; the parent's RSS watchdog covers memory

cpu, memory, file_size = map(int, sys.argv[1:4])
resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
limit("RLIMIT_AS", memory)
limit("RLIMIT_DATA", memory)
limit("RLIMIT_FSIZE", file_size)
limit("RLIMIT_NPROC", 0)
limit("RLIMIT_CORE", 0)
os.execv(sys.executable, [sys.executable, "-E", "-s", "main.py"])
"""


@dataclass(frozen=True)
class SandboxLimits:
    """Resource budget for a single run."""

    cpu_seconds: int = 5
    memory_mb: int = 256
    wall_seconds: float = 10.0
    output_bytes: int = 1_000_000
    max_returned_chars: int = 8_000


def _read_rss_mb(pid: int) -> float:
    result = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True)
    return int(result.stdout.strip() or 0) / 1024


class WorkspaceLayer:
    """Gives agents read access to a project and a sandbox holding a throwaway copy of it."""

    def __init__(self, project: Path, limits: SandboxLimits | None = None) -> None:
        self.project = project.resolve()
        self.limits = limits or SandboxLimits()

    def _resolve(self, relative_path: str) -> Path:
        target = (self.project / relative_path).resolve()
        if not target.is_relative_to(self.project):
            raise ValueError(f"path {relative_path!r} is outside the project")
        return target

    async def _list_files(self, tool_input: dict[str, Any]) -> ToolOutput:
        target = self._resolve(tool_input.get("path", "."))
        entries = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())
        return "\n".join(e for e in entries if e != "__pycache__/"), False

    async def _read_file(self, tool_input: dict[str, Any]) -> ToolOutput:
        text = self._resolve(tool_input["path"]).read_text()
        offset = int(tool_input.get("offset", 0))
        end = offset + MAX_READ_CHARS
        page = text[offset:end]
        if end < len(text):
            page += f"\n... [{len(text) - end} more characters: use offset={end}]"
        return page, False

    async def _run_python(self, tool_input: dict[str, Any]) -> ToolOutput:
        # Blocking work runs on a thread so parallel subagents don't stall each other
        return await asyncio.to_thread(self.run_python, tool_input["code"])

    def run_python(self, code: str) -> ToolOutput:
        """Run code against a throwaway copy of the project, so nothing it does persists."""
        limits = self.limits
        with tempfile.TemporaryDirectory(prefix="sandbox-") as tmp:
            workdir = Path(tmp) / "work"
            shutil.copytree(self.project, workdir)
            (workdir / "main.py").write_text(code)
            stdout_path, stderr_path = Path(tmp) / "stdout", Path(tmp) / "stderr"

            env = {"PATH": "/usr/bin:/bin", "HOME": str(workdir), "TMPDIR": str(workdir)}
            command = [
                sys.executable,
                "-I",
                "-c",
                BOOTSTRAP,
                str(limits.cpu_seconds),
                str(limits.memory_mb * 1024 * 1024),
                str(limits.output_bytes),
            ]
            with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
                process = subprocess.Popen(
                    command,
                    cwd=workdir,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                )
                violation = self._supervise(process)

            if process.returncode == -signal.SIGXCPU:
                violation = violation or "CPU time"

            stdout = stdout_path.read_text(errors="replace")[: limits.max_returned_chars]
            stderr = stderr_path.read_text(errors="replace")[: limits.max_returned_chars]

        parts = [f"exit_code: {process.returncode}"]
        if violation:
            parts.append(f"killed: exceeded the {violation} limit")
        parts.append(f"stdout:\n{stdout}" if stdout else "stdout: (empty)")
        if stderr:
            parts.append(f"stderr:\n{stderr}")
        return "\n".join(parts), bool(violation) or process.returncode != 0

    def _supervise(self, process: subprocess.Popen[bytes]) -> str | None:
        """Enforce what rlimits can't: wall-clock time, and memory where RLIMIT_AS isn't enforced."""
        start = time.monotonic()
        next_rss_sample = start
        violation: str | None = None
        while process.poll() is None:
            now = time.monotonic()
            if now - start > self.limits.wall_seconds:
                violation = "wall-clock"
            elif now >= next_rss_sample:
                next_rss_sample = now + RSS_SAMPLE_SECONDS
                if _read_rss_mb(process.pid) > self.limits.memory_mb:
                    violation = "memory"
            if violation:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                break
            time.sleep(POLL_SECONDS)
        process.wait()
        return violation

    def tools(self) -> list[Tool]:
        """Expose the project's read tools and the sandbox."""
        return [
            Tool(
                "list_files",
                "List files at a path relative to the project root.",
                {"type": "object", "properties": {"path": {"type": "string"}}},
                self._list_files,
            ),
            Tool(
                "read_file",
                f"Read a project file, {MAX_READ_CHARS} characters at a time. If it's longer, "
                "the result says which offset to pass to read the next part.",
                {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "offset": {"type": "integer"}},
                    "required": ["path"],
                },
                self._read_file,
            ),
            Tool(
                "run_python",
                "Run Python in a sandbox whose working directory is a throwaway copy of the "
                "project, so project modules can be imported. Standard library only, no child "
                "processes, and nothing persists. Returns exit code, stdout, and stderr.",
                {
                    "type": "object",
                    "properties": {"code": {"type": "string", "description": "Python source"}},
                    "required": ["code"],
                },
                self._run_python,
            ),
        ]

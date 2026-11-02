"""
Two execution tiers behind one interface.

SubprocessSandbox limits resources but shares the host's filesystem and network: portable,
fast, and good against accidents. DockerSandbox adds a real isolation boundary.
"""

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from common import setup_logging

logger = setup_logging(__name__)

POLL_SECONDS = 0.02
RSS_SAMPLE_SECONDS = 0.1
DOCKER_IMAGE = "python:3.12-slim"
OOM_KILLED_EXIT_CODE = 137

# Runs inside the child: apply the limits, then replace itself with the untrusted program.
# Doing this here instead of in subprocess's preexec_fn keeps it safe to call from threads.
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
os.execv(sys.executable, [sys.executable, "-I", "main.py"])
"""


@dataclass(frozen=True)
class SandboxLimits:
    """Resource budget for a single run."""

    cpu_seconds: int = 2
    memory_mb: int = 256
    wall_seconds: float = 5.0
    output_bytes: int = 1_000_000
    max_returned_chars: int = 8_000


@dataclass(frozen=True)
class ExecutionResult:
    """What came back from the sandbox, including which limit (if any) ended the run."""

    stdout: str
    stderr: str
    exit_code: int | None
    duration_seconds: float
    violation: str | None = None

    def to_tool_result(self) -> str:
        """Format the outcome for the model; all of it is untrusted data."""
        parts = [f"exit_code: {self.exit_code}"]
        if self.violation:
            parts.append(f"killed: exceeded the {self.violation} limit")
        parts.append(f"stdout:\n{self.stdout}" if self.stdout else "stdout: (empty)")
        if self.stderr:
            parts.append(f"stderr:\n{self.stderr}")
        return "\n".join(parts)


class Sandbox(Protocol):
    """The interface an agent depends on, so tiers can be swapped without touching the loop."""

    name: str

    def run_python(self, code: str) -> ExecutionResult:
        """Execute untrusted Python source and report what happened."""
        ...


def read_rss_mb(pid: int) -> float:
    """Return a process's resident memory in MB, or 0 once it has gone."""
    result = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True)
    return int(result.stdout.strip() or 0) / 1024


def read_capped(path: Path, max_chars: int) -> str:
    """Read at most max_chars of a child's output and say when it was cut off."""
    with path.open(errors="replace") as f:
        text = f.read(max_chars + 1)
    return text if len(text) <= max_chars else f"{text[:max_chars]}\n... [output truncated]"


def supervise(
    process: subprocess.Popen[bytes],
    start: float,
    wall_seconds: float,
    check: Callable[[], str | None],
    kill: Callable[[], None],
) -> str | None:
    """Poll a child until it exits or breaks a limit, and return the limit it broke."""
    violation: str | None = None
    while process.poll() is None:
        # A sleeping process burns no CPU, so RLIMIT_CPU alone would never end it
        violation = "wall-clock" if time.monotonic() - start > wall_seconds else check()
        if violation:
            kill()
            break
        time.sleep(POLL_SECONDS)
    process.wait()
    return violation


class SubprocessSandbox:
    """Tier 1: subprocess with rlimits, a stripped environment, and an ephemeral directory."""

    name = "subprocess"

    def __init__(self, limits: SandboxLimits | None = None) -> None:
        self.limits = limits or SandboxLimits()

    def run_python(self, code: str) -> ExecutionResult:
        """Execute code in a fresh directory that is deleted afterwards."""
        limits = self.limits
        with tempfile.TemporaryDirectory(prefix="sandbox-") as tmp:
            workdir = Path(tmp) / "work"
            workdir.mkdir()
            (workdir / "main.py").write_text(code)
            stdout_path, stderr_path = Path(tmp) / "stdout", Path(tmp) / "stderr"

            # Allowlist the environment: API keys in the parent's env never reach the child
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

            start = time.monotonic()
            # Writing to files, not pipes: a flood can't pile up in the parent's memory
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
                violation = supervise(
                    process,
                    start,
                    limits.wall_seconds,
                    check=self._memory_check(process.pid),
                    kill=lambda: self._kill_group(process.pid),
                )
            duration = time.monotonic() - start

            if process.returncode == -signal.SIGXCPU:
                violation = violation or "CPU time"

            return ExecutionResult(
                stdout=read_capped(stdout_path, limits.max_returned_chars),
                stderr=read_capped(stderr_path, limits.max_returned_chars),
                exit_code=process.returncode,
                duration_seconds=duration,
                violation=violation,
            )

    def _memory_check(self, pid: int) -> Callable[[], str | None]:
        """Sample memory from outside, which also works where RLIMIT_AS isn't enforced."""
        next_sample = 0.0

        def check() -> str | None:
            nonlocal next_sample
            if time.monotonic() < next_sample:
                return None
            next_sample = time.monotonic() + RSS_SAMPLE_SECONDS
            return "memory" if read_rss_mb(pid) > self.limits.memory_mb else None

        return check

    @staticmethod
    def _kill_group(pid: int) -> None:
        """Kill the child's whole process group, in case it managed to fork."""
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGKILL)


class DockerSandbox:
    """Tier 2: a throwaway container with no network, no capabilities, and a read-only root."""

    name = "docker"

    def __init__(self, limits: SandboxLimits | None = None, image: str = DOCKER_IMAGE) -> None:
        # The wall clock also covers container startup, so pull the image ahead of the first run
        self.limits = limits or SandboxLimits()
        self.image = image

    @staticmethod
    def is_available() -> bool:
        """Check that a Docker client exists and its daemon is reachable."""
        if not shutil.which("docker"):
            return False
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        return result.returncode == 0

    def build_command(self, container_name: str) -> list[str]:
        """Build the docker run command; the flags are the security policy."""
        limits = self.limits
        return [
            "docker",
            "run",
            "--rm",
            "-i",
            "--name",
            container_name,
            "--network",
            "none",
            "--memory",
            f"{limits.memory_mb}m",
            "--memory-swap",
            f"{limits.memory_mb}m",
            "--cpus",
            "1",
            "--pids-limit",
            "64",
            "--ulimit",
            f"cpu={limits.cpu_seconds}",
            "--read-only",
            "--tmpfs",
            "/tmp:size=16m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "65534:65534",
            self.image,
            "python",
            "-I",
            "-",
        ]

    def run_python(self, code: str) -> ExecutionResult:
        """Execute code passed on stdin, which avoids bind-mounting any host path."""
        limits = self.limits
        container_name = f"sandbox-{uuid.uuid4().hex[:12]}"

        with tempfile.TemporaryDirectory(prefix="sandbox-") as tmp:
            code_path = Path(tmp) / "main.py"
            code_path.write_text(code)
            stdout_path, stderr_path = Path(tmp) / "stdout", Path(tmp) / "stderr"

            def check_output() -> str | None:
                written = stdout_path.stat().st_size + stderr_path.stat().st_size
                return "output size" if written > limits.output_bytes else None

            def kill() -> None:
                # Killing the client would leave the container running, so kill it by name
                subprocess.run(["docker", "kill", container_name], capture_output=True)
                process.kill()

            start = time.monotonic()
            with (
                code_path.open("rb") as stdin,
                stdout_path.open("wb") as out,
                stderr_path.open("wb") as err,
            ):
                process = subprocess.Popen(
                    self.build_command(container_name), stdin=stdin, stdout=out, stderr=err
                )
                violation = supervise(process, start, limits.wall_seconds, check_output, kill)

            if process.returncode == OOM_KILLED_EXIT_CODE and not violation:
                violation = "memory"

            return ExecutionResult(
                stdout=read_capped(stdout_path, limits.max_returned_chars),
                stderr=read_capped(stderr_path, limits.max_returned_chars),
                exit_code=process.returncode,
                duration_seconds=time.monotonic() - start,
                violation=violation,
            )

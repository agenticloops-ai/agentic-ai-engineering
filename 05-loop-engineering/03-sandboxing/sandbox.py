"""
Sandbox execution backends shared by both provider scripts.

Two tiers, both real:
  - subprocess + rlimits: portable, contains accidents (runaway CPU/memory, huge
    files), strips the environment, runs in a throwaway directory. NOT a security
    boundary against a determined adversary.
  - docker: a real isolation boundary (separate namespace, no network, capped
    memory). Used automatically when Docker is available.

`preexec_fn` and `resource.setrlimit` are POSIX-only, which is fine for this
tutorial's Linux/macOS target.
"""

import resource
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

CPU_SECONDS = 5
MEMORY_BYTES = 512 * 1024 * 1024
FILE_SIZE_BYTES = 10 * 1024 * 1024
WALL_TIMEOUT = 10
MINIMAL_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}


@dataclass
class SandboxResult:
    """Outcome of running code in a sandbox."""

    stdout: str
    stderr: str
    returncode: int
    timed_out: bool
    backend: str

    def render(self) -> str:
        """Format the result for feeding back to the model."""
        if self.timed_out:
            return f"[{self.backend}] Timed out after {WALL_TIMEOUT}s"
        parts = [f"[{self.backend}] exit={self.returncode}"]
        if self.stdout:
            parts.append(f"stdout:\n{self.stdout}")
        if self.stderr:
            parts.append(f"stderr:\n{self.stderr}")
        return "\n".join(parts)


def _apply_limits() -> None:
    """Cap CPU, address space, and file size for the child process (POSIX only)."""
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_SIZE_BYTES, FILE_SIZE_BYTES))


def run_in_subprocess(code: str) -> SandboxResult:
    """Run Python code in a resource-limited subprocess with a stripped environment."""
    with tempfile.TemporaryDirectory(prefix="sandbox_") as tmp:
        script = Path(tmp) / "snippet.py"
        script.write_text(code)
        try:
            proc = subprocess.run(
                ["python", "-I", str(script)],
                cwd=tmp,
                env={**MINIMAL_ENV, "HOME": tmp},
                capture_output=True,
                text=True,
                timeout=WALL_TIMEOUT,
                preexec_fn=_apply_limits,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult("", "", -1, True, "subprocess")
        return SandboxResult(proc.stdout, proc.stderr, proc.returncode, False, "subprocess")


def docker_available() -> bool:
    """Return True if a usable Docker CLI is on PATH."""
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


def run_in_docker(code: str, image: str = "python:3.11-slim") -> SandboxResult:
    """Run Python code inside a network-isolated, memory-capped container."""
    with tempfile.TemporaryDirectory(prefix="sandbox_") as tmp:
        script = Path(tmp) / "snippet.py"
        script.write_text(code)
        try:
            proc = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--memory",
                    "256m",
                    "--cpus",
                    "1",
                    "--pids-limit",
                    "128",
                    "-v",
                    f"{script}:/snippet.py:ro",
                    image,
                    "python",
                    "-I",
                    "/snippet.py",
                ],
                capture_output=True,
                text=True,
                timeout=WALL_TIMEOUT + 20,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult("", "", -1, True, "docker")
        return SandboxResult(proc.stdout, proc.stderr, proc.returncode, False, "docker")


def run_sandboxed(code: str, prefer_docker: bool = True) -> SandboxResult:
    """Run code in Docker when available, else fall back to the subprocess sandbox."""
    if prefer_docker and docker_available():
        return run_in_docker(code)
    return run_in_subprocess(code)

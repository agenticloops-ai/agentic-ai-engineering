"""
Sandbox Attacks

Runs hostile snippets through each sandbox tier and reports what was actually contained, so
you can see the boundary of each tier instead of assuming it. Needs no API key.

Each attack is bounded on purpose: it probes for an escape and prints a marker when it gets
through, without doing any damage if the sandbox fails to stop it.
"""

import argparse
import os
import socket
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from common import setup_logging
from shared.sandbox import DockerSandbox, ExecutionResult, Sandbox, SubprocessSandbox

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)

ESCAPED = "ESCAPED"
DECOY_ENV_VAR = "SANDBOX_DEMO_SECRET"


@dataclass(frozen=True)
class Attack:
    """A snippet that prints the ESCAPED marker only if it gets past the sandbox."""

    name: str
    code: str


def build_attacks(decoy_file: Path, listener_port: int) -> list[Attack]:
    """Build attacks aimed at a decoy file and a local listener created for this run."""
    return [
        Attack(
            "Read parent's env vars",
            f"import os\nif {DECOY_ENV_VAR!r} in os.environ: print({ESCAPED!r})",
        ),
        Attack("Burn CPU forever", f"while True: pass\nprint({ESCAPED!r})"),
        Attack("Sleep forever", f"import time\ntime.sleep(60)\nprint({ESCAPED!r})"),
        Attack(
            "Allocate 1.5 GB of memory",
            "import time\nchunks = []\nfor _ in range(30):\n"
            "    chunks.append(b'x' * 50_000_000)\n    time.sleep(0.02)\n"
            f"print({ESCAPED!r})",
        ),
        Attack(
            "Write a 50 MB file",
            "with open('big.bin', 'wb') as f:\n"
            "    for _ in range(50): f.write(b'x' * 1_000_000); f.flush()\n"
            f"print({ESCAPED!r})",
        ),
        Attack(
            "Spawn a child process",
            f"import subprocess\nsubprocess.run(['/bin/echo', 'hi'], check=True)\nprint({ESCAPED!r})",
        ),
        Attack(
            "Read a file outside the workdir",
            f"print({ESCAPED!r}, open({str(decoy_file)!r}).read()[:0])",
        ),
        Attack(
            "Open a network connection",
            f"import socket\nsocket.create_connection(('127.0.0.1', {listener_port}), timeout=1)\n"
            f"print({ESCAPED!r})",
        ),
    ]


@contextmanager
def decoy_targets() -> Iterator[tuple[Path, int]]:
    """Provide a decoy file, a local listener, and a decoy env var that attacks can try to reach."""
    os.environ[DECOY_ENV_VAR] = "not-a-real-secret"
    with tempfile.TemporaryDirectory(prefix="decoy-") as tmp:
        decoy_file = Path(tmp) / "secret.txt"
        decoy_file.write_text("not a real secret")
        with socket.create_server(("127.0.0.1", 0)) as server:
            server.settimeout(0.2)
            done = threading.Event()

            def accept_connections() -> None:
                while not done.is_set():
                    try:
                        connection, _ = server.accept()
                        connection.close()
                    except TimeoutError:
                        continue

            thread = threading.Thread(target=accept_connections, daemon=True)
            thread.start()
            try:
                yield decoy_file, server.getsockname()[1]
            finally:
                done.set()
                thread.join()
    del os.environ[DECOY_ENV_VAR]


def describe(result: ExecutionResult) -> str:
    """Summarize one attack's outcome for the results table."""
    if ESCAPED in result.stdout:
        return "[red]❌ escaped[/red]"
    if result.violation:
        return f"[green]✅ killed ({result.violation})[/green]"
    last_line = (result.stderr.strip().splitlines() or ["contained"])[-1]
    return f"[green]✅ blocked[/green] [dim]{escape(last_line[:40])}[/dim]"


def main() -> None:
    """Main orchestration function."""
    parser = argparse.ArgumentParser(description="Run hostile snippets through sandbox tiers")
    parser.add_argument("--skip-docker", action="store_true", help="Run the subprocess tier only")
    args = parser.parse_args()
    console = Console()

    tiers: list[Sandbox] = [SubprocessSandbox()]
    if not args.skip_docker and DockerSandbox.is_available():
        tiers.append(DockerSandbox())
    elif not args.skip_docker:
        console.print("[yellow]Docker isn't reachable, so skipping the container tier.[/yellow]")

    limits = SubprocessSandbox().limits
    console.print(
        Panel(
            f"CPU {limits.cpu_seconds}s · memory {limits.memory_mb} MB · "
            f"wall clock {limits.wall_seconds}s · output {limits.output_bytes // 1_000_000} MB",
            title="Limits per run",
        )
    )

    table = Table(title="What each tier contains")
    table.add_column("Attack")
    for tier in tiers:
        table.add_column(tier.name)

    with decoy_targets() as (decoy_file, port):
        for attack in build_attacks(decoy_file, port):
            console.print(f"[dim]Running: {attack.name}[/dim]")
            table.add_row(attack.name, *[describe(tier.run_python(attack.code)) for tier in tiers])

    console.print(table)
    console.print(
        "\nThe subprocess tier limits [bold]how much[/bold] code can use, not "
        "[bold]what[/bold] it can touch. Its filesystem and network are still the host's."
    )


if __name__ == "__main__":
    main()

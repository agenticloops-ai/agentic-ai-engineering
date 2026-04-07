"""
Unit Testing Agents — Test Runner

Runs the full test suite for the unit testing tutorial. Demonstrates four layers
of agent testing: mock LLM responses, tool isolation, behavioral contracts,
and integration tests with response cassettes.

Tests live in tests/ and can also be run directly via pytest:
  pytest tests/ -v
"""

from pathlib import Path

import pytest
from common import setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

# Test modules and their descriptions
TEST_SUITES = [
    ("tests/test_mock_llm.py", "Mock LLM Testing", "Mock API responses, test agent loop logic"),
    ("tests/test_tools.py", "Tool Testing", "Test tool functions in isolation with edge cases"),
    (
        "tests/test_behavioral_contracts.py",
        "Behavioral Contracts",
        "Verify agent invariants (safety, termination, history)",
    ),
    (
        "tests/test_integration.py",
        "Integration Testing",
        "Record/replay API responses, snapshot regression",
    ),
]


def main() -> None:
    """Show test suite overview and run tests with human confirmation."""
    console = Console()

    console.print(
        Panel(
            "[bold cyan]Unit Testing Agents[/bold cyan]\n\n"
            "Tests the tool-use agent loop using four complementary strategies:\n"
            "  1. Mock LLM responses — deterministic agent loop testing\n"
            "  2. Tool isolation — pure function testing with edge cases\n"
            "  3. Behavioral contracts — safety, termination, history invariants\n"
            "  4. Integration — full loop with response cassettes\n\n"
            "No API keys required — everything is simulated.",
            title="01 — Unit Testing Agents",
        )
    )

    # Show available test suites
    table = Table(title="Test Suites", show_lines=True)
    table.add_column("#", width=3, justify="center")
    table.add_column("Suite", style="cyan", width=24)
    table.add_column("Description", width=50)

    for i, (_, name, desc) in enumerate(TEST_SUITES, 1):
        table.add_row(str(i), name, desc)

    console.print(table)

    # Human confirmation before executing
    console.print("\n[bold]This will run all test suites listed above.[/bold]")
    try:
        answer = console.input("[dim]Press Enter to run, or type 'q' to quit: [/dim]")
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Cancelled.[/yellow]")
        return

    if answer.strip().lower() in ("q", "quit", "exit"):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Run tests
    console.print("\n[bold]Running tests...[/bold]\n")

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / "test_results.xml"

    test_files = [str(Path(__file__).parent / path) for path, _, _ in TEST_SUITES]
    exit_code = pytest.main(
        [
            *test_files,
            "-v",
            "--tb=short",
            "--no-header",
            f"--junitxml={report_path}",
        ]
    )

    if exit_code == 0:
        console.print("\n[bold green]All tests passed![/bold green]")
    else:
        console.print(f"\n[bold red]Some tests failed (exit code: {exit_code})[/bold red]")

    console.print(f"[dim]Test report saved to {report_path}[/dim]")


if __name__ == "__main__":
    main()

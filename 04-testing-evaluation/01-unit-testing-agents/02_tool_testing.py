"""
Tool Testing

Demonstrates how to test tool functions in isolation — verifying input validation,
output format, error handling, and edge cases without involving the LLM at all.

Key testing concepts:
- Unit testing pure functions: tools are deterministic, test them directly
- Fixture-based setup: pytest fixtures for temp files and shared state
- Edge case coverage: division by zero, missing files, blocked commands, timeouts
"""

import subprocess
from pathlib import Path
from typing import Any

import pytest
from common import setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel

load_dotenv(find_dotenv())

logger = setup_logging(__name__)


# ---------------------------------------------------------------------------
# Tool functions under test (same as the reference agent implementation)
# ---------------------------------------------------------------------------

BLOCKED_COMMANDS = ["rm", "sudo", "chmod", "chown", "mkfs", "dd", "shutdown", "reboot", ">", ">>"]


def calculator(operation: str, a: float, b: float) -> dict[str, Any]:
    """Execute calculator tool."""
    operations = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else "Error: Division by zero",
    }
    if operation not in operations:
        return {"error": f"Unknown operation: {operation}"}
    result = operations[operation](a, b)
    logger.info("Calculator: %s %s %s = %s", a, operation, b, result)
    return {"result": result, "operation": operation, "operands": [a, b]}


def read_file(path: str, max_lines: int = 100) -> dict[str, Any]:
    """Read the contents of a file."""
    try:
        with Path(path).open(encoding="utf-8") as f:
            lines = f.readlines()
        total_lines = len(lines)
        content = "".join(lines[:max_lines])
        truncated = total_lines > max_lines
        logger.info("Read file: %s (%d lines)", path, total_lines)
        return {
            "path": path,
            "content": content,
            "total_lines": total_lines,
            "truncated": truncated,
        }
    except FileNotFoundError:
        return {"error": f"File not found: {path}"}
    except PermissionError:
        return {"error": f"Permission denied: {path}"}


def run_bash(command: str, timeout: int = 30) -> dict[str, Any]:
    """Execute a bash command and return the output."""
    cmd_lower = command.lower().strip()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            logger.warning("Blocked dangerous command: %s", command)
            return {"error": f"Command blocked for safety: contains '{blocked}'"}
    logger.info("Running bash command: %s", command)
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {
            "command": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout} seconds"}


# Tool dispatch mapping
TOOL_FUNCTIONS: dict[str, Any] = {
    "calculator": calculator,
    "read_file": read_file,
    "run_bash": run_bash,
}


def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> Any:
    """Execute a tool and return its result."""
    if tool_name not in TOOL_FUNCTIONS:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return TOOL_FUNCTIONS[tool_name](**tool_input)
    except TypeError as e:
        logger.error("Invalid arguments for tool %s: %s", tool_name, e)
        return {"error": f"Invalid arguments: {e}"}
    except Exception as e:
        logger.error("Tool execution error: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    """Create a temporary file with known content for testing."""
    filepath = tmp_path / "sample.txt"
    filepath.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n", encoding="utf-8")
    return filepath


@pytest.fixture()
def long_file(tmp_path: Path) -> Path:
    """Create a temporary file with many lines for truncation testing."""
    filepath = tmp_path / "long.txt"
    content = "\n".join(f"line {i}" for i in range(1, 201))
    filepath.write_text(content, encoding="utf-8")
    return filepath


# ---------------------------------------------------------------------------
# Calculator tests
# ---------------------------------------------------------------------------


class TestCalculator:
    """Tests for the calculator tool."""

    def test_calculator_add(self) -> None:
        """Verify addition returns correct result."""
        result = calculator("add", 3, 5)
        assert result["result"] == 8
        assert result["operation"] == "add"
        assert result["operands"] == [3, 5]

    def test_calculator_subtract(self) -> None:
        """Verify subtraction returns correct result."""
        result = calculator("subtract", 10, 4)
        assert result["result"] == 6

    def test_calculator_multiply(self) -> None:
        """Verify multiplication returns correct result."""
        result = calculator("multiply", 7, 8)
        assert result["result"] == 56

    def test_calculator_divide(self) -> None:
        """Verify division returns correct result."""
        result = calculator("divide", 20, 4)
        assert result["result"] == 5.0

    def test_calculator_division_by_zero(self) -> None:
        """Verify division by zero returns an error string, not an exception."""
        result = calculator("divide", 10, 0)
        assert result["result"] == "Error: Division by zero"

    def test_calculator_float_precision(self) -> None:
        """Verify calculator handles floating-point numbers."""
        result = calculator("add", 0.1, 0.2)
        assert abs(result["result"] - 0.3) < 1e-9


# ---------------------------------------------------------------------------
# File reading tests
# ---------------------------------------------------------------------------


class TestReadFile:
    """Tests for the read_file tool."""

    def test_read_file_success(self, sample_file: Path) -> None:
        """Verify successful file reading returns content and metadata."""
        result = read_file(str(sample_file))
        assert "line 1" in result["content"]
        assert result["total_lines"] == 5
        assert result["truncated"] is False

    def test_read_file_not_found(self) -> None:
        """Verify missing file returns an error dict, not an exception."""
        result = read_file("/nonexistent/path/file.txt")
        assert "error" in result
        assert "File not found" in result["error"]

    def test_read_file_truncation(self, long_file: Path) -> None:
        """Verify max_lines parameter truncates output correctly."""
        result = read_file(str(long_file), max_lines=3)
        # Only first 3 lines should be in content
        assert result["content"].count("\n") <= 3
        assert result["truncated"] is True
        assert result["total_lines"] == 200


# ---------------------------------------------------------------------------
# Bash command tests
# ---------------------------------------------------------------------------


class TestRunBash:
    """Tests for the run_bash tool."""

    def test_run_bash_success(self) -> None:
        """Verify a simple command executes and returns output."""
        result = run_bash("echo hello")
        assert result["stdout"].strip() == "hello"
        assert result["exit_code"] == 0

    def test_run_bash_blocked_commands(self) -> None:
        """Verify every blocked command is rejected before execution."""
        for cmd in BLOCKED_COMMANDS:
            result = run_bash(f"{cmd} something")
            assert "error" in result, f"Command '{cmd}' should be blocked"
            assert "blocked" in result["error"].lower()

    def test_run_bash_rm_rf_blocked(self) -> None:
        """Verify the classic dangerous command is blocked."""
        result = run_bash("rm -rf /")
        assert "error" in result
        assert "blocked" in result["error"].lower()

    def test_run_bash_timeout(self) -> None:
        """Verify timeout is enforced for long-running commands."""
        result = run_bash("sleep 10", timeout=1)
        assert "error" in result
        assert "timed out" in result["error"].lower()

    def test_run_bash_nonexistent_command(self) -> None:
        """Verify a bad command returns a non-zero exit code."""
        result = run_bash("nonexistent_command_xyz_123")
        assert result["exit_code"] != 0


# ---------------------------------------------------------------------------
# Tool dispatcher tests
# ---------------------------------------------------------------------------


class TestExecuteTool:
    """Tests for the execute_tool dispatcher."""

    def test_execute_tool_unknown_tool(self) -> None:
        """Verify unknown tool names return an error."""
        result = execute_tool("nonexistent_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_execute_tool_invalid_args(self) -> None:
        """Verify wrong arguments return an error instead of crashing."""
        # calculator requires 'operation', 'a', 'b' — pass wrong keys
        result = execute_tool("calculator", {"wrong_key": "value"})
        assert "error" in result
        assert "Invalid arguments" in result["error"]

    def test_execute_tool_dispatches_correctly(self) -> None:
        """Verify the dispatcher routes to the correct tool function."""
        result = execute_tool("calculator", {"operation": "add", "a": 1, "b": 2})
        assert result["result"] == 3

    def test_execute_tool_read_file_dispatch(self, sample_file: Path) -> None:
        """Verify the dispatcher routes read_file correctly."""
        result = execute_tool("read_file", {"path": str(sample_file)})
        assert "content" in result
        assert "line 1" in result["content"]


# ---------------------------------------------------------------------------
# main() — run tests with Rich output for standalone execution
# ---------------------------------------------------------------------------


def main() -> None:
    """Run tests programmatically and display results with Rich."""
    console = Console()

    console.print(
        Panel(
            "[bold cyan]Tool Testing[/bold cyan]\n\n"
            "Tests tool functions in isolation — no LLM, no mocks needed.\n"
            "Covers: input validation, output format, error handling, edge cases.\n\n"
            "Concepts: pure function testing, fixtures, edge case coverage",
            title="02 — Tool Testing",
        )
    )

    console.print("\n[bold]Running tests...[/bold]\n")

    # Save test results to output/
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / "02_tool_testing.xml"

    exit_code = pytest.main(
        [
            __file__,
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

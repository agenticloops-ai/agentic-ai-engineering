"""
Promptfoo — YAML-Driven Eval Framework

Demonstrates how to integrate Promptfoo with a Python-based agent. Promptfoo is a
Node.js CLI tool that supports custom Python providers and assertions, letting you
define eval suites declaratively in YAML.

This script:
1. Generates a promptfooconfig.yaml with test cases from our golden dataset
2. Creates a custom Python provider that wraps our research assistant
3. Creates a custom Python assertion for keyword grading
4. Shows how to run the eval via `npx promptfoo eval`

Note: Promptfoo requires Node.js. Install via `npm install -g promptfoo` or use
`npx promptfoo@latest eval`. The `pip install promptfoo` package wraps the Node binary.
"""

import json
from pathlib import Path

from common import setup_logging
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from shared.knowledge_base import EVAL_TASKS, get_agent_response

logger = setup_logging(__name__)


# ---------------------------------------------------------------------------
# Promptfoo YAML configuration generator
# ---------------------------------------------------------------------------


def generate_promptfoo_config(tasks: list[dict], output_dir: Path) -> str:
    """Generate a promptfooconfig.yaml for our research assistant."""
    tests = []
    for task in tasks:
        test_case: dict = {
            "vars": {"question": task["question"]},
            "assert": [],
        }

        # Code-based assertions: keyword checks via custom Python function
        if task["expected_keywords"]:
            test_case["assert"].append(
                {
                    "type": "python",
                    "value": "file://assertion_keywords.py",
                    "metadata": {"keywords": task["expected_keywords"]},
                }
            )
        else:
            # Out-of-scope: should contain a refusal
            test_case["assert"].append(
                {
                    "type": "icontains",
                    "value": "unable to find",
                }
            )

        # Source citation check
        for source_id in task.get("expected_source_ids", []):
            test_case["assert"].append(
                {
                    "type": "contains",
                    "value": source_id,
                }
            )

        # LLM-as-judge rubric (uses Promptfoo's built-in llm-rubric assertion)
        if task["expected_keywords"]:
            test_case["assert"].append(
                {
                    "type": "llm-rubric",
                    "value": (
                        f"The response should accurately answer: '{task['question']}'. "
                        f"It should cite sources and cover these topics: "
                        f"{', '.join(task['expected_keywords'])}."
                    ),
                }
            )

        tests.append(test_case)

    config = {
        "description": "Research Assistant Eval Suite",
        "providers": [
            {
                "id": "file://provider_agent.py",
                "label": "Research Assistant",
                "config": {"mode": "simulated"},
            }
        ],
        "prompts": ["{{question}}"],
        "tests": tests,
        "defaultTest": {
            "options": {
                "provider": "anthropic:messages:claude-sonnet-4-5-20250929",
            }
        },
    }

    # Write YAML config
    import yaml  # type: ignore[import-untyped]

    config_path = output_dir / "promptfooconfig.yaml"
    with config_path.open("w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    return config_path.name


def generate_provider_script(output_dir: Path) -> None:
    """Generate the custom Python provider script for Promptfoo."""
    # Promptfoo calls this script's call_api function for each test case
    provider_code = '''"""
Custom Promptfoo provider wrapping the research assistant.

Promptfoo calls call_api() for each test case. The function receives:
- prompt: the rendered prompt string
- options: dict with 'config' from YAML
- context: dict with 'vars' from the test case
"""


def call_api(prompt, options, context):
    """Promptfoo provider entry point."""
    from shared.knowledge_base import get_agent_response, EVAL_TASKS

    question = context.get("vars", {}).get("question", prompt)

    # Find matching task by question text
    task_id = None
    for task in EVAL_TASKS:
        if task["question"] == question:
            task_id = task["id"]
            break

    if task_id is None:
        return {"output": "No matching task found."}

    response = get_agent_response(task_id)

    return {
        "output": response["answer"],
        "tokenUsage": {"total": 100, "prompt": 50, "completion": 50},
    }
'''
    (output_dir / "provider_agent.py").write_text(provider_code, encoding="utf-8")


def generate_assertion_script(output_dir: Path) -> None:
    """Generate the custom Python assertion script for keyword grading."""
    assertion_code = '''"""
Custom Promptfoo assertion for keyword coverage grading.

Promptfoo calls get_assert() for each assertion of type 'python'.
Returns a dict with pass, score, and reason.
"""


def get_assert(output, context):
    """Check keyword coverage in the agent output."""
    metadata = context.get("test", {}).get("metadata", {})
    keywords = metadata.get("keywords", [])

    if not keywords:
        return {"pass": True, "score": 1.0, "reason": "No keywords to check"}

    output_lower = output.lower()
    found = [kw for kw in keywords if kw.lower() in output_lower]
    missing = [kw for kw in keywords if kw.lower() not in output_lower]

    score = len(found) / len(keywords)
    passed = score >= 0.5

    reason = f"Found {len(found)}/{len(keywords)} keywords"
    if missing:
        reason += f" (missing: {', '.join(missing)})"

    return {"pass": passed, "score": score, "reason": reason}
'''
    (output_dir / "assertion_keywords.py").write_text(assertion_code, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main — generate config and demonstrate the setup
# ---------------------------------------------------------------------------


def main() -> None:
    """Generate Promptfoo configuration and demonstrate the YAML-driven eval pattern."""
    console = Console()
    console.print(
        Panel(
            "[bold cyan]Promptfoo — YAML-Driven Eval Framework[/bold cyan]\n\n"
            "Generates a Promptfoo eval suite with:\n"
            "  - Custom Python provider (wraps our research assistant)\n"
            "  - Custom Python assertion (keyword grading)\n"
            "  - Built-in assertions (contains, icontains, llm-rubric)\n\n"
            "Promptfoo is a Node.js CLI with first-class Python support.\n"
            "Install: npm install -g promptfoo",
            title="01 - Promptfoo",
        )
    )

    output_dir = Path(__file__).parent
    try:
        import yaml  # noqa: F401  # type: ignore[import-untyped]
    except ImportError:
        console.print(
            "[yellow]PyYAML not installed — showing JSON config instead.[/yellow]\n"
            "[dim]Install with: pip install pyyaml[/dim]\n"
        )

    # Generate Promptfoo files
    generate_provider_script(output_dir)
    generate_assertion_script(output_dir)
    console.print("[green]Generated provider_agent.py and assertion_keywords.py[/green]\n")

    # Show what the config would look like
    console.print("[bold]Promptfoo Configuration (promptfooconfig.yaml)[/bold]\n")

    # Build a sample config to display (avoid yaml dependency for display)
    sample_config = {
        "description": "Research Assistant Eval Suite",
        "providers": [
            {
                "id": "file://provider_agent.py",
                "label": "Research Assistant",
                "config": {"mode": "simulated"},
            }
        ],
        "prompts": ["{{question}}"],
        "tests": [
            {
                "vars": {"question": EVAL_TASKS[0]["question"]},
                "assert": [
                    {
                        "type": "python",
                        "value": "file://assertion_keywords.py",
                        "metadata": {"keywords": EVAL_TASKS[0]["expected_keywords"]},
                    },
                    {"type": "contains", "value": "doc_001"},
                    {
                        "type": "llm-rubric",
                        "value": "The response should accurately cover microservices benefits.",
                    },
                ],
            },
            {"vars": {"question": "..."}, "assert": [{"type": "..."}]},
        ],
    }
    config_yaml = json.dumps(sample_config, indent=2)
    console.print(Syntax(config_yaml, "json", theme="monokai", line_numbers=True))

    # Try to generate YAML config if pyyaml is available
    try:
        config_name = generate_promptfoo_config(EVAL_TASKS, output_dir)
        console.print(f"\n[green]Generated {config_name}[/green]")
    except ImportError:
        console.print("\n[yellow]Skipping YAML generation (pyyaml not installed)[/yellow]")

    # Run the assertions locally to demonstrate the grading logic
    console.print("\n[bold]Running assertions locally (simulated):[/bold]\n")

    # Import the generated assertion logic inline
    for task in EVAL_TASKS:
        response = get_agent_response(task["id"])
        output = response["answer"]

        # Keyword check
        if task["expected_keywords"]:
            output_lower = output.lower()
            found = [kw for kw in task["expected_keywords"] if kw.lower() in output_lower]
            score = len(found) / len(task["expected_keywords"])
            status = "[green]PASS[/green]" if score >= 0.5 else "[red]FAIL[/red]"
            console.print(f"  {task['id']}: {status} keywords={score:.0%}", end="")
        else:
            has_refusal = "unable to find" in output.lower() or "no relevant" in output.lower()
            status = "[green]PASS[/green]" if has_refusal else "[red]FAIL[/red]"
            console.print(f"  {task['id']}: {status} refusal={has_refusal}", end="")

        # Source citation check
        for sid in task.get("expected_source_ids", []):
            cited = sid in output
            cite_status = "[green]yes[/green]" if cited else "[red]no[/red]"
            console.print(f"  {sid}={cite_status}", end="")

        console.print()

    # Show how to run
    console.print(
        "\n[bold]To run with Promptfoo CLI:[/bold]\n"
        "  [dim]npx promptfoo@latest eval[/dim]\n"
        "  [dim]npx promptfoo@latest view  # opens web UI with results[/dim]"
    )


if __name__ == "__main__":
    main()

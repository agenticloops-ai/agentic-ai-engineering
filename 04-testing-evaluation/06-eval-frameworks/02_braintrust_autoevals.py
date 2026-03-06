"""
Braintrust AutoEvals — Pre-Built Scorers for Agent Evaluation

Demonstrates using the Braintrust `autoevals` library for evaluating agent responses.
AutoEvals provides ready-to-use scorers: string similarity (local, no API key), factuality
and other LLM-based scorers (requires OpenAI key), and custom LLM classifiers.

This script:
1. Shows string-based scorers (Levenshtein, ExactMatch) — fully local
2. Demonstrates LLM-based scorers (Factuality, ClosedQA) — requires OPENAI_API_KEY
3. Builds a custom LLM classifier for domain-specific grading
4. Runs all scorers against our research assistant responses

Install: pip install autoevals
"""

import os

from common import setup_logging
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from shared.knowledge_base import EVAL_TASKS, get_agent_response

load_dotenv(find_dotenv())

logger = setup_logging(__name__)


# ---------------------------------------------------------------------------
# Simulated scorer results for demo mode (when autoevals is not installed)
# ---------------------------------------------------------------------------

SIMULATED_SCORES: dict[str, dict[str, float]] = {
    "task_001": {"levenshtein": 0.42, "factuality": 0.9, "closedqa": 0.85},
    "task_002": {"levenshtein": 0.38, "factuality": 0.95, "closedqa": 0.90},
    "task_003": {"levenshtein": 0.45, "factuality": 0.85, "closedqa": 0.80},
    "task_004": {"levenshtein": 0.51, "factuality": 0.90, "closedqa": 0.85},
    "task_005": {"levenshtein": 0.30, "factuality": 0.80, "closedqa": 0.70},
}


def run_string_scorers(output: str, expected: str, task_id: str) -> dict[str, float]:
    """Run string-based scorers (no API key needed)."""
    try:
        from autoevals import Levenshtein

        lev = Levenshtein()
        lev_result = lev.eval(output=output, expected=expected)
        return {"levenshtein": lev_result.score or 0.0}
    except ImportError:
        logger.info("autoevals not installed, using simulated scores")
        return {"levenshtein": SIMULATED_SCORES.get(task_id, {}).get("levenshtein", 0.0)}


def run_llm_scorers(question: str, output: str, expected: str, task_id: str) -> dict[str, float]:
    """Run LLM-based scorers (requires OPENAI_API_KEY)."""
    has_openai_key = bool(os.environ.get("OPENAI_API_KEY"))

    if not has_openai_key:
        logger.info("No OPENAI_API_KEY, using simulated LLM scorer results")
        sim = SIMULATED_SCORES.get(task_id, {})
        return {
            "factuality": sim.get("factuality", 0.0),
            "closedqa": sim.get("closedqa", 0.0),
        }

    try:
        from autoevals import ClosedQA, Factuality

        scores: dict[str, float] = {}

        # Factuality: checks if output is factually consistent with expected
        factuality = Factuality()
        fact_result = factuality.eval(
            input=question,
            output=output,
            expected=expected,
        )
        scores["factuality"] = fact_result.score or 0.0

        # ClosedQA: evaluates answer quality against the question
        closedqa = ClosedQA()
        cqa_result = closedqa.eval(
            input=question,
            output=output,
            expected=expected,
        )
        scores["closedqa"] = cqa_result.score or 0.0

        return scores
    except ImportError:
        logger.info("autoevals not installed, using simulated scores")
        sim = SIMULATED_SCORES.get(task_id, {})
        return {
            "factuality": sim.get("factuality", 0.0),
            "closedqa": sim.get("closedqa", 0.0),
        }
    except Exception as e:
        logger.error("LLM scorer error: %s", e)
        return {"factuality": 0.0, "closedqa": 0.0}


def run_custom_classifier(output: str, task_id: str) -> dict[str, float]:
    """Run a custom LLM classifier for source grounding."""
    has_openai_key = bool(os.environ.get("OPENAI_API_KEY"))

    if not has_openai_key:
        # Simulated: check if output contains doc_XXX pattern
        has_source = "doc_" in output
        return {"grounding": 1.0 if has_source else 0.0}

    try:
        from autoevals import LLMClassifier

        grounding_classifier = LLMClassifier(
            name="SourceGrounding",
            prompt_template=(
                "Does the following response cite specific sources (e.g., doc_001) "
                "to support its claims?\n\nResponse: {{output}}\n\n"
                "Answer Yes if sources are cited, No if not."
            ),
            choice_scores={"Yes": 1.0, "No": 0.0},
        )
        result = grounding_classifier.eval(output=output)
        return {"grounding": result.score or 0.0}
    except ImportError:
        has_source = "doc_" in output
        return {"grounding": 1.0 if has_source else 0.0}
    except Exception as e:
        logger.error("Custom classifier error: %s", e)
        return {"grounding": 0.0}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run Braintrust autoevals scorers against research assistant responses."""
    console = Console()
    console.print(
        Panel(
            "[bold cyan]Braintrust AutoEvals — Pre-Built Scorers[/bold cyan]\n\n"
            "Evaluates agent responses using:\n"
            "  - String scorers: Levenshtein similarity (local, no API key)\n"
            "  - LLM scorers: Factuality, ClosedQA (requires OPENAI_API_KEY)\n"
            "  - Custom classifier: source grounding check\n\n"
            "Install: pip install autoevals",
            title="02 - Braintrust AutoEvals",
        )
    )

    # Check what's available
    has_autoevals = False
    try:
        import autoevals  # noqa: F401

        has_autoevals = True
    except ImportError:
        pass

    has_openai_key = bool(os.environ.get("OPENAI_API_KEY"))

    if has_autoevals and has_openai_key:
        console.print("[green]autoevals installed + OpenAI key — running all scorers live[/green]")
    elif has_autoevals:
        console.print(
            "[yellow]autoevals installed, no OpenAI key — "
            "string scorers live, LLM scorers simulated[/yellow]"
        )
    else:
        console.print("[yellow]autoevals not installed — using simulated scores for demo[/yellow]")
    console.print()

    # Results table
    table = Table(title="AutoEvals Scorer Results", show_lines=True)
    table.add_column("Task", style="cyan", width=12)
    table.add_column("Levenshtein", width=12, justify="center")
    table.add_column("Factuality", width=12, justify="center")
    table.add_column("ClosedQA", width=12, justify="center")
    table.add_column("Grounding", width=12, justify="center")
    table.add_column("Avg Score", width=10, justify="center")

    all_scores: list[dict[str, float]] = []

    for task in EVAL_TASKS:
        response = get_agent_response(task["id"])
        output = response["answer"]
        expected = task["reference_answer"]

        # Run all scorer categories
        scores: dict[str, float] = {}
        scores.update(run_string_scorers(output, expected, task["id"]))
        scores.update(run_llm_scorers(task["question"], output, expected, task["id"]))
        scores.update(run_custom_classifier(output, task["id"]))

        all_scores.append(scores)

        # Format table row
        def fmt(s: float) -> str:
            color = "green" if s >= 0.7 else ("yellow" if s >= 0.4 else "red")
            return f"[{color}]{s:.2f}[/{color}]"

        avg = sum(scores.values()) / len(scores) if scores else 0.0
        avg_color = "green" if avg >= 0.7 else ("yellow" if avg >= 0.4 else "red")

        table.add_row(
            task["id"],
            fmt(scores.get("levenshtein", 0.0)),
            fmt(scores.get("factuality", 0.0)),
            fmt(scores.get("closedqa", 0.0)),
            fmt(scores.get("grounding", 0.0)),
            f"[{avg_color}]{avg:.2f}[/{avg_color}]",
        )

    console.print(table)

    # Aggregate
    if all_scores:
        console.print("\n[bold]Aggregate Scores[/bold]")
        for scorer_name in ["levenshtein", "factuality", "closedqa", "grounding"]:
            values = [s.get(scorer_name, 0.0) for s in all_scores]
            avg = sum(values) / len(values)
            console.print(f"  {scorer_name:12s}: {avg:.2f}")

    # Show code example
    console.print("\n[bold]Usage Example (standalone autoevals):[/bold]\n")
    code = (
        "from autoevals import Factuality, Levenshtein\n\n"
        "# String scorer — fully local, no API key\n"
        "lev = Levenshtein()\n"
        'result = lev.eval(output="hello wrld", expected="hello world")\n'
        "print(result.score)  # ~0.91\n\n"
        "# LLM scorer — requires OPENAI_API_KEY\n"
        "fact = Factuality()\n"
        "result = fact.eval(\n"
        '    input="What is the capital of France?",\n'
        '    output="Paris is the capital of France.",\n'
        '    expected="The capital of France is Paris.",\n'
        ")\n"
        "print(result.score)  # 1.0\n"
    )
    from rich.syntax import Syntax

    console.print(Syntax(code, "python", theme="monokai", line_numbers=True))

    # Show Braintrust Eval() pattern
    console.print("\n[bold]Full Eval Pipeline (with Braintrust platform):[/bold]\n")
    eval_code = (
        "from braintrust import Eval\n"
        "from autoevals import Factuality, Levenshtein\n\n"
        "Eval(\n"
        '    "Research Assistant Suite",\n'
        "    data=lambda: [\n"
        '        {"input": "What is microservices?", "expected": "..."},\n'
        "    ],\n"
        "    task=lambda input: my_agent.answer(input),\n"
        "    scores=[Factuality, Levenshtein],\n"
        ")\n"
    )
    console.print(Syntax(eval_code, "python", theme="monokai", line_numbers=True))


if __name__ == "__main__":
    main()

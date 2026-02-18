"""
Evaluator-Optimizer — "The Editor's Desk"

Demonstrates one LLM generating content while another evaluates it in a loop,
refining until a quality threshold is met. Generator and Evaluator have different
prompts with different goals.

Pipeline: Research (web search) → Write (no tools) → Evaluate → Refine loop
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from common import AnthropicTokenTracker, interactive_menu, setup_logging

load_dotenv(find_dotenv())
logger = setup_logging(__name__)

OUTPUT_DIR = Path("output")
MODEL = "claude-sonnet-4-20250514"
LIGHT_MODEL = "claude-haiku-4-5-20251001"

# Anthropic server-side web search tool — Claude decides when to search
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 1}

SUGGESTED_TOPICS = [
    "Building Event-Driven Microservices",
    "Edge Computing for Real-Time AI",
    "Modern CSS Layout Techniques",
    "Database Sharding Strategies",
]

# --- Prompts ---

RESEARCH_SYSTEM_PROMPT = (
    "You are a technical researcher. Use web search to find current, accurate information "
    "on the topic. Write 2-3 short paragraphs synthesizing the most relevant findings. "
    "Focus on practical details, trade-offs, and real-world patterns. No preamble."
)

WRITER_SYSTEM_PROMPT = (
    "You are a technical blog writer. Given research notes, write a concise blog post. "
    "Include an introduction, 3-5 sections with informative headers, code examples where "
    "relevant, and a conclusion. Use a professional but approachable tone. "
    "Aim for under 1000 words total — no filler, no fluff."
)

REFINER_SYSTEM_PROMPT = (
    "You are a technical blog writer. Revise the draft based on the feedback provided. "
    "Address every issue and suggestion. Maintain the overall structure but improve "
    "quality. Return the complete revised post."
)

EVALUATOR_SYSTEM_PROMPT = """\
You are a demanding technical editor. Rate content 1-10 on:

1. CLARITY: Can engineers follow without re-reading? \
(9-10: crystal clear, 7-8: minor rough spots, 5-6: requires effort)
2. TECHNICAL ACCURACY: Is info correct and current? \
(9-10: production-ready, 7-8: minor imprecisions)
3. STRUCTURE: Logical flow, easy to navigate? \
(9-10: perfect progression, scannable)
4. ENGAGEMENT: Would engineers want to read this? \
(9-10: compelling, memorable)
5. HUMAN VOICE: Does it sound like a real person? \
(9-10: natural, varied rhythm, 5-6: robotic/generic)

Be specific in feedback: "The intro is generic — open with the specific problem" \
not just "make it more engaging"."""

# 5-dimension structured evaluation output
EVALUATION_TOOLS = [
    {
        "name": "evaluate_draft",
        "description": "Evaluate a blog post draft on multiple quality dimensions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "clarity": {"type": "integer", "minimum": 1, "maximum": 10},
                "technical_accuracy": {"type": "integer", "minimum": 1, "maximum": 10},
                "structure": {"type": "integer", "minimum": 1, "maximum": 10},
                "engagement": {"type": "integer", "minimum": 1, "maximum": 10},
                "human_voice": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Does it sound like a real person?",
                },
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific issues found",
                },
                "suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Actionable improvement suggestions",
                },
            },
            "required": [
                "clarity",
                "technical_accuracy",
                "structure",
                "engagement",
                "human_voice",
                "issues",
                "suggestions",
            ],
        },
    }
]

SCORE_THRESHOLD = 7.0
MAX_REFINEMENTS = 2

# Callback type: agent emits (event_name, event_data) — caller decides how to display
EvaluatorCallback = Callable[[str, dict[str, Any]], None]

SCORE_DIMENSIONS = ["Clarity", "Technical Accuracy", "Structure", "Engagement", "Human Voice"]
SCORE_KEYS = ["clarity", "technical_accuracy", "structure", "engagement", "human_voice"]


def _extract_scores(evaluation: dict[str, Any]) -> tuple[dict[str, int], float]:
    """Extract named scores from evaluation and compute average."""
    scores = dict(zip(SCORE_DIMENSIONS, (evaluation[k] for k in SCORE_KEYS)))
    return scores, sum(scores.values()) / len(scores)


class EvaluatorOptimizer:
    """Research → Write → Evaluate → Refine loop until quality threshold is met."""

    def __init__(self, model: str, light_model: str, token_tracker: AnthropicTokenTracker):
        self.client = anthropic.Anthropic()
        self.model = model
        self.light_model = light_model
        self.token_tracker = token_tracker
        self._notify: EvaluatorCallback = lambda _e, _d: None

    def _call_llm(
        self,
        system: str,
        messages: list[dict[str, Any]],
        *,
        use_light: bool = False,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, str] | None = None,
    ) -> anthropic.types.Message:
        """Single LLM call with token tracking."""
        model = self.light_model if use_light else self.model
        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        tool_names = [t.get("name", t.get("type", "unknown")) for t in tools or []]
        logger.info("Calling %s, tools=%s", model, tool_names)

        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            **kwargs,
        )
        self.token_tracker.track(response.usage)
        return response

    def _call_llm_text(self, system: str, user_message: str, **kwargs: Any) -> str:
        """Call LLM and return the text content."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
        return cast(str, self._call_llm(system, messages, **kwargs).content[0].text)

    def _research(self, topic: str) -> str:
        """Research phase: web search gathers current data on the topic."""
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": f"Research this topic: {topic}"}
        ]
        response = self._call_llm(
            RESEARCH_SYSTEM_PROMPT,
            messages,
            use_light=True,
            max_tokens=1024,
            tools=[WEB_SEARCH_TOOL],
        )
        text_parts = [block.text for block in response.content if block.type == "text"]
        return "\n\n".join(text_parts)

    def _write(self, topic: str, research: str) -> str:
        """Write phase: synthesize from research data — no tools, no web search."""
        user_msg = f"Research:\n{research}\n\nWrite a blog post about: {topic}"
        return self._call_llm_text(WRITER_SYSTEM_PROMPT, user_msg, use_light=True)

    def _refine(self, topic: str, draft: str, research: str, evaluation: dict[str, Any]) -> str:
        """Refine phase: rewrite from feedback — no tools."""
        feedback = (
            f"Issues: {json.dumps(evaluation['issues'])}\n"
            f"Suggestions: {json.dumps(evaluation['suggestions'])}"
        )
        user_msg = (
            f"Topic: {topic}\n\n"
            f"Research:\n{research}\n\n"
            f"Feedback to address:\n{feedback}\n\n"
            f"Previous draft:\n{draft}\n\n"
            "Revise the draft to address all feedback."
        )
        return self._call_llm_text(REFINER_SYSTEM_PROMPT, user_msg)

    def _evaluate(self, draft: str, topic: str) -> dict[str, Any]:
        """Evaluator: score the draft on 3 dimensions and provide feedback."""
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": f"Topic: {topic}\n\nDraft to evaluate:\n\n{draft}"}
        ]
        response = self._call_llm(
            EVALUATOR_SYSTEM_PROMPT,
            messages,
            use_light=True,
            max_tokens=1024,
            tools=EVALUATION_TOOLS,
            tool_choice={"type": "tool", "name": "evaluate_draft"},
        )

        for block in response.content:
            if block.type == "tool_use":
                return cast(dict[str, Any], block.input)

        raise ValueError("Evaluator did not return structured evaluation")

    def run(self, topic: str, on_event: EvaluatorCallback | None = None) -> str:
        """Run the full pipeline: research → write → evaluate → refine loop."""
        self._notify = on_event or (lambda _e, _d: None)

        # Step 1: Research (web search gathers data)
        self._notify("research_start", {})
        research = self._research(topic)
        self.token_tracker.report()
        self._notify("research_complete", {"chars": len(research)})

        # Step 2: Write (from research data, no tools)
        self._notify("write_start", {})
        draft = self._write(topic, research)
        self._notify("draft_complete", {"chars": len(draft)})

        # Step 3: Evaluate → Refine loop
        for iteration in range(1, MAX_REFINEMENTS + 1):
            self._notify("evaluate_start", {"iteration": iteration})
            evaluation = self._evaluate(draft, topic)
            scores, avg_score = _extract_scores(evaluation)
            self.token_tracker.report()

            self._notify(
                "evaluation_complete",
                {
                    "iteration": iteration,
                    "scores": scores,
                    "avg": avg_score,
                    "issues": evaluation.get("issues", []),
                    "suggestions": evaluation.get("suggestions", []),
                },
            )

            if avg_score >= SCORE_THRESHOLD:
                self._notify("threshold_met", {"avg": avg_score})
                break

            if iteration < MAX_REFINEMENTS:
                self._notify("refining", {"avg": avg_score})
                draft = self._refine(topic, draft, research, evaluation)
                self._notify("draft_complete", {"chars": len(draft)})
            else:
                self._notify("max_iterations", {"avg": avg_score})

        return draft


def main() -> None:
    """Run the evaluator-optimizer demo."""
    console = Console()
    token_tracker = AnthropicTokenTracker()

    def on_event(event: str, data: dict[str, Any]) -> None:
        """Handle pipeline events for console display."""
        if event == "research_start":
            console.print("\n[bold yellow]Researching:[/bold yellow] Gathering current data...")
        elif event == "research_complete":
            console.print(f"  [green]✓[/green] Research: {data['chars']} chars")
        elif event == "write_start":
            console.print("\n[bold yellow]Writing:[/bold yellow] Generating initial draft...")
        elif event == "draft_complete":
            console.print(f"  [green]✓[/green] Draft: {data['chars']} chars")
        elif event == "evaluate_start":
            console.print(
                f"\n[bold yellow]Evaluating:[/bold yellow] Round {data['iteration']}"
                f"/{MAX_REFINEMENTS}..."
            )
        elif event == "evaluation_complete":
            scores = data["scores"]
            avg = data["avg"]
            table = Table(title=f"Evaluation (avg: {avg:.1f}/10)")
            table.add_column("Dimension", style="cyan")
            table.add_column("Score", justify="center")
            for dim, score in scores.items():
                color = "green" if score >= 8 else "yellow" if score >= 6 else "red"
                table.add_row(dim, f"[{color}]{score}/10[/{color}]")
            console.print(table)
            if data["issues"]:
                console.print("[bold red]Issues:[/bold red]")
                for issue in data["issues"]:
                    console.print(f"  [red]•[/red] {issue}")
            if data.get("suggestions"):
                console.print("[bold yellow]Suggestions:[/bold yellow]")
                for suggestion in data["suggestions"]:
                    console.print(f"  [yellow]•[/yellow] {suggestion}")
        elif event == "threshold_met":
            console.print(f"\n[green]Score {data['avg']:.1f} >= {SCORE_THRESHOLD} — done![/green]")
        elif event == "refining":
            console.print(
                f"[yellow]Score {data['avg']:.1f} < {SCORE_THRESHOLD} — refining...[/yellow]"
            )
        elif event == "max_iterations":
            console.print(f"\n[yellow]Max iterations reached (score: {data['avg']:.1f})[/yellow]")

    header = Panel(
        "[bold cyan]Evaluator-Optimizer — The Editor's Desk[/bold cyan]\n\n"
        "Topic → [Researcher] → data\n"
        "      → [Writer] → draft (from research, no web search)\n"
        "      → [Evaluator] → 5-dimension score + feedback\n"
        f"      → Score >= {SCORE_THRESHOLD}? → Done\n"
        "      → Below threshold → [Refiner] → Loop\n\n"
        f"Max {MAX_REFINEMENTS} refinements. "
        "Scores: clarity, accuracy, structure, engagement, human voice (1-10)",
        title="Evaluator-Optimizer",
    )

    try:
        while True:
            topic = interactive_menu(
                console,
                SUGGESTED_TOPICS,
                title="Select a Topic",
                header=header,
                allow_custom=True,
                custom_prompt="Enter your topic",
            )
            if not topic:
                break

            console.print(f"\n[bold green]Topic:[/bold green] {topic}")
            eo = EvaluatorOptimizer(MODEL, LIGHT_MODEL, token_tracker)

            try:
                result = eo.run(topic, on_event=on_event)

                OUTPUT_DIR.mkdir(exist_ok=True)
                slug = topic.lower().replace(" ", "_")[:50]
                path = OUTPUT_DIR / f"{slug}.md"
                path.write_text(result, encoding="utf-8")

                console.print("\n[bold blue]Final Article:[/bold blue]")
                console.print(Markdown(result))
                abs_path = path.resolve()
                console.print(f"\n[dim]Saved to [link=file://{abs_path}]{path}[/link][/dim]")

                console.print("\n[dim]Press Enter to continue...[/dim]")
                input()
            except Exception as e:
                logger.error("Evaluator-optimizer failed: %s", e)
                console.print(f"\n[red]Error: {e}[/red]")
            finally:
                token_tracker.reset()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")


if __name__ == "__main__":
    main()

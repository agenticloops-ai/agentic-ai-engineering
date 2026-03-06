"""
Orchestrator-Workers — "The Deep Dive Researcher"

Demonstrates a central LLM dynamically breaking down a task, delegating subtasks
to worker LLMs, and synthesizing their results into a final article.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, cast

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from common import AnthropicTokenTracker, interactive_menu, setup_logging

load_dotenv(find_dotenv())
logger = setup_logging(__name__)

OUTPUT_DIR = Path("output")
MODEL = "claude-sonnet-4-6"
LIGHT_MODEL = "claude-haiku-4-5-20251001"

# Anthropic server-side web search tool — Claude decides when to search
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 1}

SUGGESTED_TOPICS = [
    "Compare Bun vs Node.js for Backend Development",
    "Python 3.13 New Features and Performance",
    "WebAssembly in Production: State of the Art",
    "AI Code Review Tools Landscape 2025",
]

# --- Prompts ---

ORCHESTRATOR_SYSTEM_PROMPT = (
    "You are a research orchestrator. Given a topic, break it down into 2-4 specific "
    "research subtopics that can be investigated independently. Each subtopic should "
    "cover a distinct dimension of the topic. Think like a journalist who would "
    "research each angle separately before writing."
)

WORKER_SYSTEM_PROMPT = (
    "You are a thorough technical researcher. Research the given topic in depth. "
    "Provide specific details, examples, comparisons, and data points where possible. "
    "Write 3-4 paragraphs of substantive analysis. "
    "Use web search if the topic would benefit from current information."
)

SYNTHESIZER_SYSTEM_PROMPT = (
    "You are a senior technical writer. Given research from multiple sources on different "
    "subtopics, synthesize them into a cohesive, well-structured article."
)

# Tool for the orchestrator to decompose tasks
PLANNING_TOOLS = [
    {
        "name": "create_research_plan",
        "description": "Break down a topic into specific research subtopics for workers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subtopics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Subtopic title",
                            },
                            "research_prompt": {
                                "type": "string",
                                "description": "Specific research question for the worker",
                            },
                        },
                        "required": ["title", "research_prompt"],
                    },
                    "description": "List of subtopics to research in parallel",
                },
                "synthesis_instructions": {
                    "type": "string",
                    "description": "Instructions for how to combine the research into a final article",
                },
            },
            "required": ["subtopics", "synthesis_instructions"],
        },
    }
]

# Callback type: agent emits (event_name, event_data) — caller decides how to display
OrchestratorCallback = Callable[[str, dict[str, Any]], None]


class OrchestratorWorkers:
    """Orchestrator decomposes tasks dynamically, workers execute in parallel."""

    def __init__(self, model: str, light_model: str, token_tracker: AnthropicTokenTracker):
        self.client = anthropic.Anthropic()
        self.model = model
        self.light_model = light_model
        self.token_tracker = token_tracker
        self._notify: OrchestratorCallback = lambda _e, _d: None

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

    def _plan(self, topic: str) -> dict[str, Any]:
        """Orchestrator: dynamically decompose the topic into subtopics."""
        logger.info("Orchestrator planning: %s", topic)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": f"Plan research for: {topic}"}
        ]
        response = self._call_llm(
            ORCHESTRATOR_SYSTEM_PROMPT,
            messages,
            max_tokens=1024,
            tools=PLANNING_TOOLS,
            tool_choice={"type": "tool", "name": "create_research_plan"},
        )

        for block in response.content:
            if block.type == "tool_use":
                return cast(dict[str, Any], block.input)

        raise ValueError("Orchestrator did not produce a research plan")

    def _research_subtopic(self, subtopic: dict[str, str]) -> dict[str, str]:
        """Worker: research a single subtopic in depth, optionally using web search."""
        title = subtopic["title"]
        logger.info("Worker researching: %s", title)

        messages: list[dict[str, Any]] = [{"role": "user", "content": subtopic["research_prompt"]}]
        response = self._call_llm(
            WORKER_SYSTEM_PROMPT, messages, use_light=True, tools=[WEB_SEARCH_TOOL]
        )
        text_parts = [block.text for block in response.content if block.type == "text"]
        return {"title": title, "content": "\n\n".join(text_parts)}

    def _synthesize(self, topic: str, research: list[dict[str, str]], instructions: str) -> str:
        """Synthesizer: combine all worker research into a coherent final article."""
        logger.info("Synthesizing %d research sections", len(research))
        sections = "\n\n---\n\n".join(f"## {r['title']}\n\n{r['content']}" for r in research)
        system = f"{SYNTHESIZER_SYSTEM_PROMPT} Synthesis instructions: {instructions}"
        user_msg = (
            f"# {topic}\n\nResearch sections:\n\n{sections}\n\n"
            "Synthesize into a complete, coherent article."
        )
        return self._call_llm_text(system, user_msg)

    def run(self, topic: str, on_event: OrchestratorCallback | None = None) -> str:
        """Execute the full orchestrator-workers pipeline."""
        self._notify = on_event or (lambda _e, _d: None)

        # Step 1: Orchestrator plans
        self._notify("plan_start", {})
        plan = self._plan(topic)
        subtopics = plan["subtopics"]
        instructions = plan["synthesis_instructions"]
        self.token_tracker.report()
        self._notify("plan_complete", {"subtopics": subtopics})

        # Step 2: Workers research in parallel
        self._notify("workers_start", {"count": len(subtopics)})
        research_results: list[dict[str, str]] = []

        with ThreadPoolExecutor(max_workers=len(subtopics)) as executor:
            futures = {
                executor.submit(self._research_subtopic, sub): sub["title"] for sub in subtopics
            }
            for future in as_completed(futures):
                title = futures[future]
                try:
                    result = future.result()
                    research_results.append(result)
                    self._notify("worker_complete", {"title": title})
                except Exception as e:
                    logger.error("Worker failed on %s: %s", title, e)

        self.token_tracker.report()

        # Step 3: Synthesize
        self._notify("synthesize_start", {})
        final = self._synthesize(topic, research_results, instructions)
        self.token_tracker.report()
        self._notify("synthesize_complete", {})

        return final


def main() -> None:
    """Run the orchestrator-workers demo."""
    console = Console()
    token_tracker = AnthropicTokenTracker()

    def on_event(event: str, data: dict[str, Any]) -> None:
        """Handle pipeline events for console display."""
        if event == "plan_start":
            console.print("\n[bold yellow]Orchestrator:[/bold yellow] Planning research...")
        elif event == "plan_complete":
            subtopics = data["subtopics"]
            console.print(
                Panel(
                    "\n".join(f"• {s['title']}" for s in subtopics),
                    title=f"Research Plan ({len(subtopics)} subtopics)",
                    border_style="cyan",
                )
            )
        elif event == "workers_start":
            console.print(
                f"\n[bold yellow]Workers:[/bold yellow] "
                f"Researching {data['count']} subtopics in parallel..."
            )
        elif event == "worker_complete":
            console.print(f"  [green]✓[/green] {data['title']}")
        elif event == "synthesize_start":
            console.print("\n[bold yellow]Synthesizer:[/bold yellow] Combining research...")
        elif event == "synthesize_complete":
            console.print("  [green]✓[/green] Done")

    header = Panel(
        "[bold cyan]Orchestrator-Workers — The Deep Dive Researcher[/bold cyan]\n\n"
        "Topic → [Orchestrator] → Dynamic subtopic list\n"
        "      → [Worker 1] + [Worker 2] + [Worker N] (parallel)\n"
        "      → [Synthesizer] → Final Article\n\n"
        "The LLM decides what to research — you define worker capabilities, not tasks.",
        title="Orchestrator-Workers",
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
            orch = OrchestratorWorkers(MODEL, LIGHT_MODEL, token_tracker)

            try:
                result = orch.run(topic, on_event=on_event)

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
                logger.error("Orchestration failed: %s", e)
                console.print(f"\n[red]Error: {e}[/red]")
            finally:
                token_tracker.reset()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")


if __name__ == "__main__":
    main()

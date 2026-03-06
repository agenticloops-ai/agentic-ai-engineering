"""
Prompt Chaining — "The Tech Blog Assembly Line"

Demonstrates decomposing a task into a sequence of fixed steps, where each LLM call
processes the output of the previous one. A topic flows through Outliner → Writer → Editor.
"""

from collections.abc import Callable
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
    "Practical Async Programming in Python",
    "AI Agents in Production",
    "WebAssembly Beyond the Browser",
    "Zero-Trust Security for Startups",
]


# --- Prompts ---

OUTLINER_SYSTEM_PROMPT = (
    "You are a research planner. Given a topic, identify 3-5 broad research areas that "
    "cover distinct dimensions of the subject — market landscape, technical depth, "
    "adoption patterns, performance analysis, etc. Each area should be independently "
    "researchable. Output the topic title on the first line, then the research areas "
    "as bullet points. Keep area names short and high-level. No extra commentary."
)
OUTLINER_USER_PROMPT = "Create a blog outline for: {topic}"

WRITER_SYSTEM_PROMPT = (
    "You are a technical blog writer. Given an outline (title + bullet points), write a "
    "concise blog post. Use the title as an H1 heading and each bullet point as an H2 "
    "section. Write 1-2 short paragraphs per section — no filler, no fluff. "
    "Use a professional but approachable tone. Aim for under 1000 words total. "
    "Always use web search to ground your writing with current, accurate information."
)
WRITER_USER_PROMPT = "Write a full blog post from this outline:\n\n{outline}"

EDITOR_SYSTEM_PROMPT = (
    "You are a professional editor. Polish the given blog post for grammar, clarity, and "
    "flow. At the end, add a '## Key Takeaways' section with 3-5 bullet points summarizing "
    "the main insights. Return the complete edited post."
)
EDITOR_USER_PROMPT = "Edit and polish this blog post:\n\n{draft}"

# Callback type: agent emits (event_name, event_data) — caller decides how to display
ChainCallback = Callable[[str, dict[str, Any]], None]


class PromptChain:
    """Sequential chain of LLM calls where each step feeds into the next."""

    def __init__(self, model: str, light_model: str, token_tracker: AnthropicTokenTracker):
        self.client = anthropic.Anthropic()
        self.model = model
        self.light_model = light_model
        self.token_tracker = token_tracker
        self._notify: ChainCallback = lambda _e, _d: None

    def _call_llm(
        self,
        system: str,
        messages: list[dict[str, Any]],
        *,
        use_light: bool = False,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
    ) -> anthropic.types.Message:
        """Single LLM call with token tracking."""
        model = self.light_model if use_light else self.model
        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools
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

    def _call_llm_text(self, system: str, user_message: str) -> str:
        """Call LLM and return the text content."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
        return cast(str, self._call_llm(system, messages).content[0].text)

    def _run_agentic_loop(
        self,
        system: str,
        user_message: str,
        *,
        use_light: bool = False,
        tools: list[dict[str, Any]] | None = None,
    ) -> tuple[str, list[dict[str, str]]]:
        """Run LLM with tool use, continuing across multiple turns if needed."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
        searches: list[dict[str, str]] = []

        response = self._call_llm(system, messages, use_light=use_light, tools=tools)

        for _ in range(4):
            # Collect search results from this turn
            for block in response.content:
                if block.type == "web_search_tool_result" and isinstance(block.content, list):
                    for result in block.content:
                        searches.append({"title": result.title, "url": result.url})

            if response.stop_reason == "end_turn":
                break

            # Continue the conversation with tool results
            messages.append({"role": "assistant", "content": response.content})
            tool_results = [
                {"type": "tool_result", "tool_use_id": b.id, "content": "Search completed."}
                for b in response.content
                if b.type == "tool_use"
            ]
            if not tool_results:
                break
            messages.append({"role": "user", "content": tool_results})

            response = self._call_llm(system, messages, use_light=use_light, tools=tools)

        text_parts = [b.text for b in response.content if b.type == "text"]
        return "\n\n".join(text_parts), searches

    def _step_outline(self, topic: str) -> str:
        """Step 1: Generate a structured outline with title and bullet points."""
        return self._call_llm_text(OUTLINER_SYSTEM_PROMPT, OUTLINER_USER_PROMPT.format(topic=topic))

    def _step_write(self, outline: str) -> tuple[str, list[dict[str, str]]]:
        """Step 2: Expand the outline into a full blog post, optionally using web search."""
        return self._run_agentic_loop(
            WRITER_SYSTEM_PROMPT,
            WRITER_USER_PROMPT.format(outline=outline),
            use_light=True,
            tools=[WEB_SEARCH_TOOL],
        )

    def _step_edit(self, draft: str) -> str:
        """Step 3: Polish the draft and add a Key Takeaways section."""
        return self._call_llm_text(EDITOR_SYSTEM_PROMPT, EDITOR_USER_PROMPT.format(draft=draft))

    def run(self, topic: str, on_event: ChainCallback | None = None) -> str:
        """Execute the full chain: Outline → Write → Edit."""
        self._notify = on_event or (lambda _e, _d: None)

        # Step 1: Outline
        self._notify("step_start", {"name": "Outline"})
        outline = self._step_outline(topic)
        if not outline.strip():
            raise ValueError("Outliner produced empty output — aborting chain.")
        self.token_tracker.report()
        self._notify("step_complete", {"name": "Outline", "result": outline})

        # Step 2: Write
        self._notify("step_start", {"name": "Write"})
        logger.info("[Write] Calling %s", self.light_model)
        draft, searches = self._step_write(outline)
        self.token_tracker.report()
        self._notify("step_complete", {"name": "Write", "searches": searches})

        # Step 3: Edit
        self._notify("step_start", {"name": "Edit"})
        final = self._step_edit(draft)
        self.token_tracker.report()
        self._notify("step_complete", {"name": "Edit"})

        self._notify("chain_complete", {})
        return final


def main() -> None:
    """Run the prompt chaining demo."""
    console = Console()
    token_tracker = AnthropicTokenTracker()

    def on_chain_event(event: str, data: dict[str, Any]) -> None:
        """Print step progress to console."""
        if event == "step_start":
            console.print(f"  [cyan]{data['name']}...[/cyan]")
        elif event == "step_complete":
            console.print("  [green]✓[/green] Done")
            if data["name"] == "Outline" and data.get("result"):
                console.print(Panel(data["result"], title="Outline", border_style="dim"))
            if data["name"] == "Write" and data.get("searches"):
                lines = [
                    f"  [dim]•[/dim] [link={s['url']}]{s['title']}[/link]" for s in data["searches"]
                ]
                console.print(Panel("\n".join(lines), title="Sources", border_style="dim"))

    header = Panel(
        "[bold cyan]Prompt Chaining — The Tech Blog Assembly Line[/bold cyan]\n\n"
        "Topic → [Outliner] → [Writer] → [Editor] → Final Post\n\n"
        "Each step feeds its output to the next.",
        title="Prompt Chaining",
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
            chain = PromptChain(MODEL, LIGHT_MODEL, token_tracker)

            try:
                result = chain.run(topic, on_event=on_chain_event)

                # Save article to output directory
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
                logger.error("Chain failed: %s", e)
                console.print(f"\n[red]Error: {e}[/red]")
            finally:
                token_tracker.reset()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")


if __name__ == "__main__":
    main()

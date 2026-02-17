"""
Routing — "The Content Strategist"

Demonstrates routing to specialized handlers based on content classification.
An LLM classifier determines content type, then dispatches to the appropriate
specialized chain (Tutorial, News, or Concept Explainer).
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
MODEL = "claude-sonnet-4-20250514"
LIGHT_MODEL = "claude-haiku-4-5-20251001"

SUGGESTED_TOPICS = [
    "How to deploy a FastAPI app on AWS Lambda",
    "Python 3.13 removed the GIL",
    "What is retrieval-augmented generation (RAG)",
    "How to set up CI/CD with GitHub Actions",
]

# --- Classification schema for structured output ---

CLASSIFY_TOOLS = [
    {
        "name": "classify_content",
        "description": "Classify the content type of a given topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content_type": {
                    "type": "string",
                    "enum": ["tutorial", "news", "concept"],
                    "description": (
                        "tutorial: how-to guides (e.g. 'How to install Docker'). "
                        "news: announcements or changes (e.g. 'Docker changed its licensing'). "
                        "concept: explanations of ideas (e.g. 'What is containerization')."
                    ),
                },
                "reasoning": {
                    "type": "string",
                    "description": "Brief explanation of why this classification was chosen.",
                },
            },
            "required": ["content_type", "reasoning"],
        },
    }
]

# --- Prompts ---

CLASSIFY_SYSTEM_PROMPT = "Classify the following topic into one of: tutorial, news, or concept."

# Route chain steps

# Tutorial route
TUTORIAL_PREREQS_PROMPT = (
    "You are a technical writer. List the prerequisites needed before starting this "
    "tutorial. Be specific about versions and tools. Output a bulleted list."
)
TUTORIAL_STEPS_PROMPT = (
    "You are a technical writer. Given these prerequisites and a topic, write a clear "
    "step-by-step guide. Number each step. Include code examples where relevant."
)
TUTORIAL_TROUBLESHOOTING_PROMPT = (
    "You are a technical support writer. Given a tutorial, add a troubleshooting section "
    "with 3-5 common issues and their solutions. Format as '### Problem' / '**Solution**'."
)

# News route
NEWS_SUMMARY_PROMPT = (
    "You are a tech journalist. Summarize the key changes or news. Be factual and concise. "
    "Use bullet points for each distinct change."
)
NEWS_IMPACT_PROMPT = (
    "You are a technology analyst. Given this summary of changes, analyze the impact on "
    "developers and teams. Cover: who is affected, what changes, migration considerations."
)
NEWS_CTA_PROMPT = (
    "You are a tech editor. Given the news and impact analysis, write a brief call to "
    "action section telling readers what they should do next. Be specific and actionable."
)

# Concept route
CONCEPT_ANALOGY_PROMPT = (
    "You are a tech educator. Explain the given concept using a clear, relatable analogy. "
    "Start with the analogy, then bridge to the technical concept."
)
CONCEPT_ARCHITECTURE_PROMPT = (
    "You are a software architect. Given the concept introduction, describe the technical "
    "architecture in detail. Include how components interact and common implementations."
)
CONCEPT_PROS_CONS_PROMPT = (
    "You are a pragmatic engineer. Given the concept and architecture, list the pros and "
    "cons. Be honest about trade-offs. Format as two bullet lists."
)

# Callback type: router emits (event_name, event_data) — caller decides how to display
RouterCallback = Callable[[str, dict[str, Any]], None]


class ContentRouter:
    """Routes topics to specialized content generation chains based on classification."""

    def __init__(self, model: str, light_model: str, token_tracker: AnthropicTokenTracker):
        self.client = anthropic.Anthropic()
        self.model = model
        self.light_model = light_model
        self.token_tracker = token_tracker
        self._notify: RouterCallback = lambda _e, _d: None

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

    def _call_llm_text(self, system: str, user_message: str, *, use_light: bool = False) -> str:
        """Call LLM and return the text content."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
        return cast(str, self._call_llm(system, messages, use_light=use_light).content[0].text)

    def _classify(self, topic: str) -> dict[str, str]:
        """Classify the topic using tool-based structured output (Haiku)."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": topic}]
        response = self._call_llm(
            CLASSIFY_SYSTEM_PROMPT,
            messages,
            use_light=True,
            max_tokens=256,
            tools=CLASSIFY_TOOLS,
            tool_choice={"type": "tool", "name": "classify_content"},
        )

        for block in response.content:
            if block.type == "tool_use":
                return cast(dict[str, str], block.input)

        raise ValueError("Classifier did not return a tool call")

    def _chain_tutorial(self, topic: str) -> str:
        """Tutorial chain: Prerequisites → Step-by-Step → Troubleshooting."""
        self._notify("step_start", {"name": "Prerequisites"})
        prerequisites = self._call_llm_text(
            TUTORIAL_PREREQS_PROMPT,
            f"What prerequisites are needed for: {topic}",
        )
        self._notify("step_complete", {"name": "Prerequisites"})

        self._notify("step_start", {"name": "Steps"})
        steps = self._call_llm_text(
            TUTORIAL_STEPS_PROMPT,
            f"Topic: {topic}\n\nPrerequisites:\n{prerequisites}\n\nWrite the step-by-step guide.",
            use_light=True,
        )
        self._notify("step_complete", {"name": "Steps"})

        self._notify("step_start", {"name": "Troubleshooting"})
        troubleshooting = self._call_llm_text(
            TUTORIAL_TROUBLESHOOTING_PROMPT,
            f"Add troubleshooting for this tutorial:\n\n{steps}",
        )
        self._notify("step_complete", {"name": "Troubleshooting"})
        return (
            f"# {topic}\n\n"
            f"## Prerequisites\n\n{prerequisites}\n\n"
            f"## Step-by-Step Guide\n\n{steps}\n\n"
            f"## Troubleshooting\n\n{troubleshooting}"
        )

    def _chain_news(self, topic: str) -> str:
        """News chain: Summary of Changes → Impact Analysis → Call to Action."""
        self._notify("step_start", {"name": "Summary"})
        summary = self._call_llm_text(
            NEWS_SUMMARY_PROMPT,
            f"Summarize the changes: {topic}",
        )
        self._notify("step_complete", {"name": "Summary"})

        # Middle step: straightforward expansion from structured context
        self._notify("step_start", {"name": "Impact"})
        impact = self._call_llm_text(
            NEWS_IMPACT_PROMPT,
            f"Analyze the impact of these changes:\n\n{summary}",
            use_light=True,
        )
        self._notify("step_complete", {"name": "Impact"})

        self._notify("step_start", {"name": "Call to Action"})
        cta = self._call_llm_text(
            NEWS_CTA_PROMPT,
            f"News: {summary}\n\nImpact: {impact}\n\nWrite the call to action.",
        )
        self._notify("step_complete", {"name": "Call to Action"})

        return (
            f"# {topic}\n\n"
            f"## What Changed\n\n{summary}\n\n"
            f"## Impact Analysis\n\n{impact}\n\n"
            f"## What You Should Do\n\n{cta}"
        )

    def _chain_concept(self, topic: str) -> str:
        """Concept chain: Analogy → Architecture Description → Pros/Cons."""
        self._notify("step_start", {"name": "Analogy"})
        analogy = self._call_llm_text(
            CONCEPT_ANALOGY_PROMPT,
            f"Explain with an analogy: {topic}",
        )
        self._notify("step_complete", {"name": "Analogy"})

        # Middle step: straightforward expansion from structured context
        self._notify("step_start", {"name": "Architecture"})
        architecture = self._call_llm_text(
            CONCEPT_ARCHITECTURE_PROMPT,
            f"Concept intro: {analogy}\n\nNow describe the architecture of: {topic}",
            use_light=True,
        )
        self._notify("step_complete", {"name": "Architecture"})

        self._notify("step_start", {"name": "Pros/Cons"})
        pros_cons = self._call_llm_text(
            CONCEPT_PROS_CONS_PROMPT,
            f"Architecture: {architecture}\n\nList pros and cons of: {topic}",
        )
        self._notify("step_complete", {"name": "Pros/Cons"})

        return (
            f"# {topic}\n\n"
            f"## Understanding the Concept\n\n{analogy}\n\n"
            f"## Architecture\n\n{architecture}\n\n"
            f"## Pros and Cons\n\n{pros_cons}"
        )

    def run(self, topic: str, on_event: RouterCallback | None = None) -> str:
        """Classify the topic, route to the appropriate chain, and return the result."""
        self._notify = on_event or (lambda _e, _d: None)

        # Step 1: Classify
        self._notify("classify_start", {})
        classification = self._classify(topic)
        content_type = classification["content_type"]
        reasoning = classification["reasoning"]
        self.token_tracker.report()
        self._notify("classify_complete", {"content_type": content_type, "reasoning": reasoning})

        # Step 2: Route to specialized chain
        routes: dict[str, Callable[[str], str]] = {
            "tutorial": self._chain_tutorial,
            "news": self._chain_news,
            "concept": self._chain_concept,
        }

        chain_fn = routes.get(content_type)
        if not chain_fn:
            raise ValueError(f"Unknown content type: {content_type}")

        self._notify("chain_start", {"content_type": content_type})
        result = chain_fn(topic)
        self.token_tracker.report()
        self._notify("chain_complete", {"content_type": content_type})

        return result


def main() -> None:
    """Run the routing demo."""
    console = Console()
    token_tracker = AnthropicTokenTracker()

    def on_router_event(event: str, data: dict[str, Any]) -> None:
        """Render router events to the console."""
        if event == "classify_start":
            console.print("\n[bold yellow]Step 1:[/bold yellow] Classifying topic...")
        elif event == "classify_complete":
            console.print(
                Panel(
                    f"[bold]{data['content_type'].upper()}[/bold]\n{data['reasoning']}",
                    title="Classification",
                    border_style="cyan",
                )
            )
        elif event == "chain_start":
            console.print(
                f"\n[bold yellow]Step 2:[/bold yellow] Running {data['content_type']} chain..."
            )
        elif event == "step_start":
            console.print(f"  [cyan]{data['name']}...[/cyan]")
        elif event == "step_complete":
            console.print("  [green]\u2713[/green] Done")

    header = Panel(
        "[bold cyan]Routing \u2014 The Content Strategist[/bold cyan]\n\n"
        "Topic \u2192 [Classifier] \u2192 Route [bold]A[/bold], [bold]B[/bold], or [bold]C[/bold] \u2192 [Specialized Chain] \u2192 Post\n\n"
        "[bold]A.[/bold] Tutorial (how-to):  Prerequisites \u2192 Steps \u2192 Troubleshooting\n"
        "[bold]B.[/bold] News/Announcement:  Changes \u2192 Impact \u2192 Call to Action\n"
        "[bold]C.[/bold] Concept Explainer:  Analogy \u2192 Architecture \u2192 Pros/Cons",
        title="Routing Demo",
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
            router = ContentRouter(MODEL, LIGHT_MODEL, token_tracker)

            try:
                result = router.run(topic, on_event=on_router_event)

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
                logger.error("Routing failed: %s", e)
                console.print(f"\n[red]Error: {e}[/red]")
            finally:
                token_tracker.reset()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")


if __name__ == "__main__":
    main()

"""
Parallelization — "The Social Media Blast"

Demonstrates fan-out for independent work and fan-in to combine results.
Takes a blog post and generates social media content in parallel, plus a voting
pattern for SEO title selection.
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

MODEL = "claude-sonnet-4-20250514"
INPUT_DIR = Path("input")
OUTPUT_DIR = Path("output")

# --- Prompts ---

LINKEDIN_SYSTEM_PROMPT = (
    "You are a LinkedIn content specialist. Write a professional summary of the given "
    "blog post suitable for LinkedIn. Include relevant hashtags. Keep it under 300 words."
)

TWITTER_SYSTEM_PROMPT = (
    "You are a Twitter/X content specialist. Create a thread of exactly 5 tweets from the "
    "given blog post. Each tweet should be under 280 characters. Number them 1/5 through "
    "5/5. Make the first tweet a hook."
)

NEWSLETTER_SYSTEM_PROMPT = (
    "You are an email marketing specialist. Given a blog post, write: 1) A compelling "
    "email subject line, 2) A 2-3 sentence preview/intro paragraph that entices readers "
    "to click through. Format as 'Subject: ...' followed by the intro."
)

SEO_TITLE_SYSTEM_PROMPT = (
    "You are an SEO specialist. Generate exactly ONE compelling SEO title for this blog "
    "post. The title should be 50-60 characters, include relevant keywords, and be "
    "click-worthy. Output only the title, nothing else."
)

SEO_EVALUATOR_SYSTEM_PROMPT = (
    "You are an SEO evaluator. Given candidate titles and the blog post summary, pick "
    "the best title. Consider: keyword relevance, click appeal, length, and clarity. "
    "Output only the number and the winning title."
)

# Callback type: generator emits (event_name, event_data) — caller decides how to display
GeneratorCallback = Callable[[str, dict[str, Any]], None]


class ParallelContentGenerator:
    """Fan-out content generation across multiple independent LLM calls."""

    def __init__(self, model: str, token_tracker: AnthropicTokenTracker):
        self.client = anthropic.Anthropic()
        self.model = model
        self.token_tracker = token_tracker
        self._notify: GeneratorCallback = lambda _e, _d: None

    def _call_llm(self, system: str, user_message: str, temperature: float = 1.0) -> str:
        """Make a single LLM call."""
        logger.info("Calling %s (temp=%.1f)", self.model, temperature)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        self.token_tracker.track(response.usage)
        return cast(str, response.content[0].text)

    def _write_linkedin(self, blog_post: str) -> str:
        """Generate a LinkedIn professional summary."""
        return self._call_llm(
            LINKEDIN_SYSTEM_PROMPT,
            f"Create a LinkedIn post from this blog post:\n\n{blog_post}",
        )

    def _write_twitter(self, blog_post: str) -> str:
        """Generate a Twitter/X thread of 5 tweets."""
        return self._call_llm(
            TWITTER_SYSTEM_PROMPT,
            f"Create a tweet thread from this blog post:\n\n{blog_post}",
        )

    def _write_newsletter(self, blog_post: str) -> str:
        """Generate a newsletter subject line and intro paragraph."""
        return self._call_llm(
            NEWSLETTER_SYSTEM_PROMPT,
            f"Create a newsletter intro from this blog post:\n\n{blog_post}",
        )

    def _generate_seo_title(self, blog_post: str, temperature: float) -> str:
        """Generate a single SEO title candidate at a given temperature."""
        return self._call_llm(
            SEO_TITLE_SYSTEM_PROMPT,
            f"Generate an SEO title for:\n\n{blog_post[:500]}",
            temperature=temperature,
        )

    def _vote_best_title(self, titles: list[str], blog_post: str) -> str:
        """Use an evaluator to pick the best SEO title from candidates."""
        titles_text = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
        return self._call_llm(
            SEO_EVALUATOR_SYSTEM_PROMPT,
            f"Blog summary: {blog_post[:300]}\n\nCandidate titles:\n{titles_text}\n\n"
            "Which is the best SEO title and why?",
        )

    def run(self, blog_post: str, on_event: GeneratorCallback | None = None) -> dict[str, str]:
        """Execute the full parallelization pipeline."""
        self._notify = on_event or (lambda _e, _d: None)
        results: dict[str, str] = {}

        # Fan-out: run all writers concurrently
        self._notify("fanout_start", {})
        writers = {
            "linkedin": self._write_linkedin,
            "twitter": self._write_twitter,
            "newsletter": self._write_newsletter,
        }

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(fn, blog_post): name for name, fn in writers.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result()
                    self._notify("writer_complete", {"name": name})
                except Exception as e:
                    logger.error("Writer %s failed: %s", name, e)
                    results[name] = f"Error: {e}"
        self.token_tracker.report()

        # Voting pattern: generate 3 SEO titles with different temperatures
        self._notify("voting_start", {})
        temperatures = [0.3, 0.7, 1.0]
        titles: list[str] = []

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures_list = [
                executor.submit(self._generate_seo_title, blog_post, temp) for temp in temperatures
            ]
            for future in as_completed(futures_list):
                try:
                    title = future.result().strip()
                    titles.append(title)
                    self._notify("title_candidate", {"title": title})
                except Exception as e:
                    logger.error("Title generation failed: %s", e)
        self.token_tracker.report()

        # Evaluate and pick the best title
        if titles:
            self._notify("evaluating_start", {})
            results["seo_vote"] = self._vote_best_title(titles, blog_post)
            self.token_tracker.report()

        self._notify("pipeline_complete", {})
        return results


def _load_input_files() -> dict[str, Path]:
    """Discover blog posts from the input directory, keyed by display name."""
    if not INPUT_DIR.exists():
        return {}
    posts: dict[str, Path] = {}
    for path in sorted(INPUT_DIR.glob("*.md")):
        label = f"{path.stem.replace('_', ' ').title()}  [grey50]({path})[/grey50]"
        posts[label] = path
    return posts


def _clean_label(label: str) -> str:
    """Strip Rich markup from a menu label to get the plain article name."""
    return label.split("  [grey50]")[0]


def main() -> None:
    """Run the parallelization demo."""
    console = Console()
    token_tracker = AnthropicTokenTracker()
    generator = ParallelContentGenerator(MODEL, token_tracker)

    def on_event(event: str, data: dict[str, Any]) -> None:
        """Print pipeline progress to console."""
        if event == "fanout_start":
            console.print(
                "\n[bold yellow]Fan-out:[/bold yellow] Generating social content in parallel..."
            )
        elif event == "writer_complete":
            console.print(f"  [green]✓[/green] {data['name']} complete")
        elif event == "voting_start":
            console.print("\n[bold yellow]Voting:[/bold yellow] Generating SEO title candidates...")
        elif event == "title_candidate":
            console.print(f"  [dim]• {data['title']}[/dim]")
        elif event == "evaluating_start":
            console.print("\n[bold yellow]Evaluating:[/bold yellow] Picking best SEO title...")

    # Load pre-built blog posts from input/
    input_files = _load_input_files()
    labels = list(input_files.keys())

    header = Panel(
        "[bold cyan]Parallelization — The Social Media Blast[/bold cyan]\n\n"
        "Blog Post → [LinkedIn Writer] + [Twitter Writer] + [Newsletter Writer]\n"
        "         → [Aggregator] → Promo Pack\n\n"
        "Also: Voting pattern — 3 SEO titles at different temperatures → evaluator picks best",
        title="Parallelization",
    )

    try:
        while True:
            choice = interactive_menu(
                console,
                labels,
                title="Select a Blog Post",
                header=header,
                allow_custom=True,
                custom_label="✏️  Paste your own...",
                custom_prompt="Enter a short blog topic (or paste text)",
            )
            if not choice:
                break

            # Resolve blog post content
            name = _clean_label(choice) if choice in input_files else choice
            if choice in input_files:
                blog_post = input_files[choice].read_text(encoding="utf-8")
                console.print(f"\n[bold green]Blog Post:[/bold green] {name}")
            elif len(choice) < 200:
                # Short custom input — use as-is (topic or short post)
                blog_post = choice
                console.print(f"\n[bold green]Topic:[/bold green] {name}")
            else:
                blog_post = choice
                console.print(f"\n[bold green]Custom post:[/bold green] ({len(choice)} chars)")

            try:
                results = generator.run(blog_post, on_event=on_event)

                # Save promo pack to output directory
                OUTPUT_DIR.mkdir(exist_ok=True)
                slug = name.lower().replace(" ", "_")[:50]
                path = OUTPUT_DIR / f"{slug}_promo.md"
                output_parts = [f"# Promo Pack: {name}\n"]
                for key, value in results.items():
                    output_parts.append(f"## {key.upper()}\n\n{value}\n")
                path.write_text("\n".join(output_parts), encoding="utf-8")

                console.print("\n[bold blue]Promo Pack:[/bold blue]")
                for key, value in results.items():
                    console.print(Panel(Markdown(value), title=key.upper(), border_style="cyan"))

                abs_path = path.resolve()
                console.print(f"\n[dim]Saved to [link=file://{abs_path}]{path}[/link][/dim]")

                console.print("\n[dim]Press Enter to continue...[/dim]")
                input()
            except Exception as e:
                logger.error("Parallelization failed: %s", e)
                console.print(f"\n[red]Error: {e}[/red]")
            finally:
                token_tracker.report()
                token_tracker.reset()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")


if __name__ == "__main__":
    main()

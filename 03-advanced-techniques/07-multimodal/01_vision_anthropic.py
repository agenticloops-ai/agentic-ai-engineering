"""
Vision Analysis with Claude

Demonstrates how to send images to Claude for visual understanding — the most
fundamental multimodal skill. Supports URL-based images, local file analysis,
and multi-image comparison.
"""

import base64
import mimetypes
from pathlib import Path
from typing import Any

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from common import AnthropicTokenTracker, interactive_menu, setup_logging

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

MODEL = "claude-sonnet-4-6"

# Publicly accessible sample images from Wikimedia Commons
SAMPLE_IMAGES = {
    "Architecture — Colosseum": (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/"
        "d/de/Colosseo_2020.jpg/1280px-Colosseo_2020.jpg"
    ),
    "Chart — World Population": (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/"
        "b/b7/Population_curve.svg/1280px-Population_curve.svg.png"
    ),
    "Nature — Aurora Borealis": (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/"
        "a/aa/Polarlicht_2.jpg/1280px-Polarlicht_2.jpg"
    ),
}

ANALYSIS_TYPES = {
    "Describe": "Describe this image in detail. What do you see?",
    "OCR / Text Extraction": (
        "Extract all text visible in this image. Preserve the layout as closely as possible."
    ),
    "Detailed Analysis": (
        "Provide a detailed analysis of this image including: composition, colors, "
        "subjects, mood, and any notable details. If it's a chart or document, explain "
        "the data or content."
    ),
}


class VisionAnalyst:
    """Analyzes images using Claude's vision capabilities."""

    def __init__(self, model: str, token_tracker: AnthropicTokenTracker) -> None:
        self.client = anthropic.Anthropic()
        self.model = model
        self.token_tracker = token_tracker

    def analyze_url(self, image_url: str, prompt: str) -> str:
        """Analyze an image from a URL."""
        logger.info("Analyzing image URL: %s", image_url[:80])

        # Image content block with URL source — Claude fetches the image directly
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "url", "url": image_url},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        self.token_tracker.track(response.usage)
        logger.info(
            "Tokens — input: %d, output: %d",
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        result: str = response.content[0].text
        return result

    def analyze_file(self, image_path: str, prompt: str) -> str:
        """Analyze a local image file using base64 encoding."""
        logger.info("Analyzing local file: %s", image_path)

        image_data, media_type = self._encode_image(image_path)

        # Image content block with base64 source — image data sent inline
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        self.token_tracker.track(response.usage)
        logger.info(
            "Tokens — input: %d, output: %d",
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        result: str = response.content[0].text
        return result

    def compare_images(self, image_urls: list[str], prompt: str) -> str:
        """Compare multiple images in a single request."""
        logger.info("Comparing %d images", len(image_urls))

        # Build content blocks: interleave image blocks with text labels
        content: list[dict[str, Any]] = []
        for i, url in enumerate(image_urls, 1):
            content.append({"type": "text", "text": f"Image {i}:"})
            content.append(
                {
                    "type": "image",
                    "source": {"type": "url", "url": url},
                }
            )

        content.append({"type": "text", "text": prompt})

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": content}],
        )

        self.token_tracker.track(response.usage)
        logger.info(
            "Tokens — input: %d, output: %d",
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        result: str = response.content[0].text
        return result

    def _encode_image(self, image_path: str) -> tuple[str, str]:
        """Read a local image file, return (base64_data, media_type)."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Detect MIME type from file extension
        mime_type, _ = mimetypes.guess_type(str(path))
        if mime_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            raise ValueError(f"Unsupported image type: {mime_type}. Use JPEG, PNG, GIF, or WebP.")

        data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        logger.info("Encoded %s (%s, %d bytes)", path.name, mime_type, path.stat().st_size)
        return data, mime_type


def main() -> None:
    """Interactive vision analysis demo."""
    console = Console()
    token_tracker = AnthropicTokenTracker()
    analyst = VisionAnalyst(MODEL, token_tracker)

    welcome = Panel(
        "[bold cyan]Vision Analysis with Claude[/bold cyan]\n\n"
        "Send images to Claude for visual understanding:\n"
        "  [green]•[/green] Analyze sample images from URLs\n"
        "  [green]•[/green] Analyze local image files (base64)\n"
        "  [green]•[/green] Compare multiple images side by side\n\n"
        "[dim]Images cost ~1,600 tokens per 1568×1568 px[/dim]",
        title="Multimodal — Vision",
        border_style="blue",
    )

    image_menu_items = [
        *list(SAMPLE_IMAGES.keys()),
        "Compare All Samples",
        "Local File...",
    ]

    analysis_menu_items = list(ANALYSIS_TYPES.keys())

    try:
        while True:
            # Step 1: Select image source
            image_choice = interactive_menu(
                console,
                image_menu_items,
                title="Select Image",
                header=welcome,
                allow_custom=True,
                custom_label="Custom URL...",
                custom_prompt="Enter image URL",
            )

            if image_choice is None:
                break

            # Step 2: Select analysis type
            analysis_choice = interactive_menu(
                console,
                analysis_menu_items,
                title="Select Analysis Type",
                allow_custom=True,
                custom_label="Custom Prompt...",
                custom_prompt="Enter your analysis prompt",
            )

            if analysis_choice is None:
                continue

            prompt = ANALYSIS_TYPES.get(analysis_choice, analysis_choice)

            # Step 3: Execute analysis
            console.clear()
            console.print("\n[yellow]Analyzing...[/yellow]\n")

            try:
                if image_choice == "Compare All Samples":
                    urls = list(SAMPLE_IMAGES.values())
                    result = analyst.compare_images(urls, prompt)
                elif image_choice == "Local File...":
                    console.print("[bold green]Enter file path:[/bold green] ", end="")
                    file_path = input().strip()
                    if not file_path:
                        continue
                    result = analyst.analyze_file(file_path, prompt)
                elif image_choice in SAMPLE_IMAGES:
                    url = SAMPLE_IMAGES[image_choice]
                    result = analyst.analyze_url(url, prompt)
                else:
                    # Custom URL entered by user
                    result = analyst.analyze_url(image_choice, prompt)

                # Display result
                console.print(
                    Panel(
                        Markdown(result),
                        title=f"[bold blue]Analysis: {analysis_choice}[/bold blue]",
                        border_style="green",
                    )
                )

                # Token summary for this call
                table = Table(show_header=False, box=None)
                table.add_column(style="dim")
                table.add_column(style="dim")
                table.add_row("Input tokens", f"{token_tracker.get_input_tokens():,}")
                table.add_row("Output tokens", f"{token_tracker.get_output_tokens():,}")
                table.add_row("Total tokens", f"{token_tracker.get_total_tokens():,}")
                console.print(table)

            except FileNotFoundError as e:
                console.print(f"\n[red]Error: {e}[/red]")
            except ValueError as e:
                console.print(f"\n[red]Error: {e}[/red]")
            except anthropic.APIError as e:
                logger.error("API error: %s", e)
                console.print(f"\n[red]API Error: {e}[/red]")

            console.print("\n[dim]Press Enter to continue...[/dim]")
            input()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")

    # Final token report
    console.print()
    token_tracker.report()


if __name__ == "__main__":
    main()

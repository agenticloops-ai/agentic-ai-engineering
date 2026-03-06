"""
Image Generation with Gemini

Demonstrates native image generation using Google Gemini — a single model that both
understands and creates images. No separate endpoint needed; just set response_modalities
to include IMAGE.
"""

from datetime import datetime
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from google import genai
from google.genai import types
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from common import GeminiTokenTracker, interactive_menu, setup_logging

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

# Gemini model with native image generation support
MODEL = "gemini-2.0-flash-exp-image-generation"

SAMPLE_PROMPTS = {
    "Landscape": (
        "A serene mountain lake at sunrise with mist rising from the water, "
        "pine trees reflected in the still surface, photorealistic style"
    ),
    "Portrait": (
        "A watercolor portrait of a jazz musician playing saxophone, "
        "warm tones, expressive brushstrokes, artistic style"
    ),
    "Abstract": (
        "Abstract geometric art with bold primary colors, overlapping circles "
        "and triangles, clean lines, modern minimalist style"
    ),
    "Product": (
        "A minimalist product photo of a ceramic coffee mug on a wooden table, "
        "soft natural lighting, shallow depth of field, studio quality"
    ),
    "Architecture": (
        "A futuristic building with vertical gardens and glass facades, "
        "surrounded by trees, blue sky, architectural visualization style"
    ),
}

OUTPUT_DIR = Path("output")


class ImageGenerator:
    """Generates images using Gemini's native image generation."""

    def __init__(self, model: str, token_tracker: GeminiTokenTracker) -> None:
        # genai.Client() reads GOOGLE_API_KEY from environment automatically
        self.client = genai.Client()
        self.model = model
        self.token_tracker = token_tracker

    def generate(self, prompt: str) -> tuple[str, bytes | None]:
        """Generate an image from a text prompt.

        Returns (text_response, image_bytes) — image_bytes is None if generation failed.
        """
        logger.info("Generating image for prompt: %s", prompt[:60])

        # The key: response_modalities=["TEXT", "IMAGE"] requests mixed output
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )

        # Track token usage via Gemini's usage_metadata
        if response.usage_metadata:
            self.token_tracker.track(response.usage_metadata)
            logger.info(
                "Tokens — input: %d, output: %d",
                response.usage_metadata.prompt_token_count or 0,
                response.usage_metadata.candidates_token_count or 0,
            )

        # Parse response parts — can contain text and/or inline_data (image)
        text_parts: list[str] = []
        image_bytes: bytes | None = None

        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if part.text:
                    text_parts.append(part.text)
                elif part.inline_data:
                    # inline_data contains .data (bytes) and .mime_type
                    image_bytes = part.inline_data.data
                    logger.info(
                        "Received image: %s, %d bytes",
                        part.inline_data.mime_type,
                        len(image_bytes),
                    )

        text_response = "\n".join(text_parts) if text_parts else "Image generated successfully."
        return text_response, image_bytes

    def save_image(self, image_bytes: bytes, filename: str | None = None) -> str:
        """Save generated image to the output directory."""
        OUTPUT_DIR.mkdir(exist_ok=True)

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"generated_{timestamp}.png"

        file_path = OUTPUT_DIR / filename
        file_path.write_bytes(image_bytes)
        logger.info("Saved image to %s (%d bytes)", file_path, len(image_bytes))
        return str(file_path)


def main() -> None:
    """Interactive image generation demo."""
    console = Console()
    token_tracker = GeminiTokenTracker()
    generator = ImageGenerator(MODEL, token_tracker)

    welcome = Panel(
        "[bold cyan]Image Generation with Gemini[/bold cyan]\n\n"
        "Generate images from text prompts using Gemini's native generation:\n"
        "  [green]•[/green] A single model that understands AND creates images\n"
        "  [green]•[/green] No separate image API — uses generate_content\n"
        "  [green]•[/green] Images saved to output/ directory\n\n"
        "[dim]Requires GOOGLE_API_KEY in .env[/dim]",
        title="Multimodal — Image Generation",
        border_style="blue",
    )

    prompt_items = list(SAMPLE_PROMPTS.keys())

    try:
        while True:
            # Select or enter a prompt
            choice = interactive_menu(
                console,
                prompt_items,
                title="Select Prompt",
                header=welcome,
                allow_custom=True,
                custom_label="Custom Prompt...",
                custom_prompt="Describe the image you want to generate",
            )

            if choice is None:
                break

            prompt = SAMPLE_PROMPTS.get(choice, choice)

            console.clear()
            console.print(Panel(prompt, title="[bold]Prompt[/bold]", border_style="cyan"))
            console.print("\n[yellow]Generating image... (this may take a moment)[/yellow]\n")

            try:
                text_response, image_bytes = generator.generate(prompt)

                if image_bytes:
                    file_path = generator.save_image(image_bytes)
                    console.print(
                        Panel(
                            Markdown(text_response),
                            title="[bold blue]Gemini Response[/bold blue]",
                            border_style="green",
                        )
                    )
                    console.print(f"\n[bold green]Image saved:[/bold green] {file_path}")
                    console.print(f"[dim]Size: {len(image_bytes):,} bytes[/dim]")
                else:
                    console.print(
                        Panel(
                            Markdown(text_response),
                            title="[bold blue]Gemini Response[/bold blue]",
                            border_style="yellow",
                        )
                    )
                    console.print("[yellow]No image was generated in the response.[/yellow]")

                # Token summary
                table = Table(show_header=False, box=None)
                table.add_column(style="dim")
                table.add_column(style="dim")
                table.add_row("Input tokens", f"{token_tracker.get_input_tokens():,}")
                table.add_row("Output tokens", f"{token_tracker.get_output_tokens():,}")
                table.add_row("Total tokens", f"{token_tracker.get_total_tokens():,}")
                console.print(table)

            except Exception as e:
                logger.error("Generation error: %s", e)
                console.print(f"\n[red]Error: {e}[/red]")

            console.print("\n[dim]Press Enter to continue...[/dim]")
            input()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")

    # Final token report
    console.print()
    token_tracker.report()


if __name__ == "__main__":
    main()

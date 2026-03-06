"""
Voice Assistant with OpenAI Audio

Demonstrates text-to-speech and speech-to-text using OpenAI's audio APIs.
Features TTS with 6 voice options, Whisper transcription, and a round-trip
demo that converts text → speech → transcription for verification.
"""

from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from common import interactive_menu, setup_logging

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
VOICE_DESCRIPTIONS = {
    "alloy": "Neutral, balanced",
    "echo": "Warm, conversational",
    "fable": "Expressive, narrative",
    "onyx": "Deep, authoritative",
    "nova": "Energetic, friendly",
    "shimmer": "Clear, gentle",
}

TTS_MODEL = "tts-1"
STT_MODEL = "whisper-1"

SAMPLE_TEXTS = {
    "Greeting": "Hello! I'm your AI voice assistant. I can speak in six different voices.",
    "Story": (
        "Once upon a time, in a land of infinite possibilities, "
        "a small robot learned to speak. Its first words were: 'I think, therefore I am.'"
    ),
    "Technical": (
        "The transformer architecture uses self-attention mechanisms to process "
        "sequences in parallel, achieving state-of-the-art results in natural language processing."
    ),
    "Poetry": (
        "Two roads diverged in a yellow wood, and sorry I could not travel both, "
        "I took the one less traveled by, and that has made all the difference."
    ),
}

OUTPUT_DIR = Path("output")


class VoiceAssistant:
    """Handles text-to-speech and speech-to-text via OpenAI."""

    def __init__(self) -> None:
        self.client = OpenAI()
        # OpenAI audio APIs don't return token usage — track API calls instead
        # TTS is priced per character, STT (Whisper) per audio minute
        self.api_call_count = 0

    def speak(self, text: str, voice: str = "alloy") -> str:
        """Convert text to speech and save as MP3."""
        logger.info("TTS: voice=%s, text=%s", voice, text[:50])

        OUTPUT_DIR.mkdir(exist_ok=True)
        file_path = OUTPUT_DIR / f"tts_{voice}_{self.api_call_count}.mp3"

        response = self.client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=text,
        )

        response.write_to_file(str(file_path))
        self.api_call_count += 1

        file_size = file_path.stat().st_size
        logger.info("Saved audio: %s (%d bytes)", file_path, file_size)
        return str(file_path)

    def transcribe(self, audio_path: str) -> str:
        """Transcribe an audio file to text using Whisper."""
        logger.info("STT: transcribing %s", audio_path)

        with open(audio_path, "rb") as audio_file:
            transcription = self.client.audio.transcriptions.create(
                model=STT_MODEL,
                file=audio_file,
            )

        self.api_call_count += 1
        logger.info("Transcription: %s", transcription.text[:80])
        result: str = transcription.text
        return result

    def round_trip(self, text: str, voice: str = "alloy") -> tuple[str, str]:
        """Text → speech → transcribe. Returns (audio_path, transcription)."""
        logger.info("Round-trip: voice=%s", voice)

        audio_path = self.speak(text, voice)
        transcription = self.transcribe(audio_path)

        return audio_path, transcription

    def voice_comparison(self, text: str) -> list[tuple[str, str]]:
        """Generate the same text in all 6 voices. Returns list of (voice, path)."""
        logger.info("Voice comparison: generating %d voices", len(VOICES))

        results: list[tuple[str, str]] = []
        for voice in VOICES:
            path = self.speak(text, voice)
            results.append((voice, path))

        return results


def main() -> None:
    """Interactive voice assistant demo."""
    console = Console()
    assistant = VoiceAssistant()

    welcome = Panel(
        "[bold cyan]Voice Assistant with OpenAI Audio[/bold cyan]\n\n"
        "Text-to-speech and speech-to-text capabilities:\n"
        "  [green]•[/green] TTS — convert text to speech with 6 voices\n"
        "  [green]•[/green] STT — transcribe audio files with Whisper\n"
        "  [green]•[/green] Round-trip — text → speech → transcribe → compare\n"
        "  [green]•[/green] Voice comparison — hear all 6 voices\n\n"
        "[dim]Audio files saved to output/ directory[/dim]",
        title="Multimodal — Audio",
        border_style="blue",
    )

    menu_items = [
        "TTS Demo",
        "Voice Comparison",
        "Round-Trip Verification",
        "Transcribe File",
    ]

    try:
        while True:
            choice = interactive_menu(
                console,
                menu_items,
                title="Select Mode",
                header=welcome,
            )

            if choice is None:
                break

            console.clear()

            try:
                if choice == "TTS Demo":
                    _handle_tts_demo(console, assistant)

                elif choice == "Voice Comparison":
                    _handle_voice_comparison(console, assistant)

                elif choice == "Round-Trip Verification":
                    _handle_round_trip(console, assistant)

                elif choice == "Transcribe File":
                    _handle_transcription(console, assistant)

            except Exception as e:
                logger.error("Error: %s", e)
                console.print(f"\n[red]Error: {e}[/red]")

            console.print("\n[dim]Press Enter to continue...[/dim]")
            input()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")

    # Report API call count (audio APIs don't use tokens)
    console.print(f"\n[dim]Total API calls: {assistant.api_call_count}[/dim]")


def _handle_tts_demo(console: Console, assistant: VoiceAssistant) -> None:
    """Text-to-speech with voice and text selection."""
    # Select text
    text_choice = interactive_menu(
        console,
        list(SAMPLE_TEXTS.keys()),
        title="Select Text",
        allow_custom=True,
        custom_label="Custom Text...",
        custom_prompt="Enter text to speak",
    )
    if text_choice is None:
        return

    text = SAMPLE_TEXTS.get(text_choice, text_choice)

    # Select voice
    voice_items = [f"{v} — {VOICE_DESCRIPTIONS[v]}" for v in VOICES]
    voice_choice = interactive_menu(console, voice_items, title="Select Voice")
    if voice_choice is None:
        return

    voice = voice_choice.split(" — ")[0]

    console.clear()
    console.print(f"\n[yellow]Generating speech with '{voice}' voice...[/yellow]\n")

    file_path = assistant.speak(text, voice)

    console.print(
        Panel(
            f"[bold]Voice:[/bold] {voice} ({VOICE_DESCRIPTIONS[voice]})\n"
            f"[bold]Text:[/bold] {text}\n"
            f"[bold]File:[/bold] {file_path}",
            title="[bold green]Audio Generated[/bold green]",
            border_style="green",
        )
    )


def _handle_voice_comparison(console: Console, assistant: VoiceAssistant) -> None:
    """Generate the same text in all 6 voices."""
    text_choice = interactive_menu(
        console,
        list(SAMPLE_TEXTS.keys()),
        title="Select Text for Comparison",
        allow_custom=True,
        custom_label="Custom Text...",
        custom_prompt="Enter text to compare across voices",
    )
    if text_choice is None:
        return

    text = SAMPLE_TEXTS.get(text_choice, text_choice)

    console.clear()
    console.print(f"\n[yellow]Generating {len(VOICES)} voice samples...[/yellow]\n")

    results = assistant.voice_comparison(text)

    table = Table(title="Voice Comparison Results")
    table.add_column("Voice", style="cyan")
    table.add_column("Description", style="dim")
    table.add_column("File", style="green")

    for voice, path in results:
        table.add_row(voice, VOICE_DESCRIPTIONS[voice], path)

    console.print(table)
    console.print(f"\n[dim]Text: {text}[/dim]")


def _handle_round_trip(console: Console, assistant: VoiceAssistant) -> None:
    """Text → speech → transcribe → compare."""
    text_choice = interactive_menu(
        console,
        list(SAMPLE_TEXTS.keys()),
        title="Select Text for Round-Trip",
        allow_custom=True,
        custom_label="Custom Text...",
        custom_prompt="Enter text for round-trip test",
    )
    if text_choice is None:
        return

    text = SAMPLE_TEXTS.get(text_choice, text_choice)

    # Select voice
    voice_items = [f"{v} — {VOICE_DESCRIPTIONS[v]}" for v in VOICES]
    voice_choice = interactive_menu(console, voice_items, title="Select Voice")
    if voice_choice is None:
        return

    voice = voice_choice.split(" — ")[0]

    console.clear()
    console.print("\n[yellow]Running round-trip: text → speech → transcription...[/yellow]\n")

    audio_path, transcription = assistant.round_trip(text, voice)

    # Compare original and transcribed text
    original_lower = text.lower().strip()
    transcribed_lower = transcription.lower().strip()
    match = original_lower == transcribed_lower

    console.print(
        Panel(
            Markdown(
                f"**Original:** {text}\n\n"
                f"**Transcribed:** {transcription}\n\n"
                f"**Audio file:** {audio_path}\n\n"
                f"**Match:** {
                    'Exact match'
                    if match
                    else 'Differences detected (this is normal — '
                    'Whisper may adjust punctuation or capitalization)'
                }"
            ),
            title="[bold blue]Round-Trip Results[/bold blue]",
            border_style="green" if match else "yellow",
        )
    )


def _handle_transcription(console: Console, assistant: VoiceAssistant) -> None:
    """Transcribe an existing audio file."""
    console.print("\n[bold green]Enter path to audio file:[/bold green] ", end="")
    audio_path = input().strip()

    if not audio_path:
        return

    if not Path(audio_path).exists():
        console.print(f"[red]File not found: {audio_path}[/red]")
        return

    console.print(f"\n[yellow]Transcribing {audio_path}...[/yellow]\n")

    transcription = assistant.transcribe(audio_path)

    console.print(
        Panel(
            Markdown(transcription),
            title="[bold blue]Transcription[/bold blue]",
            border_style="green",
        )
    )


if __name__ == "__main__":
    main()

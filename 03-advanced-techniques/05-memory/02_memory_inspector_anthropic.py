"""Memory Inspector — browse, search, and manage persisted memories without LLM calls.

A utility tool for inspecting the episodic (JSON) and semantic (ChromaDB) memory stores
created by the memory agent. Useful for debugging, auditing, and understanding what
your agent remembers.
"""

from datetime import timezone

import readchar
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from common import setup_logging
from common.menu import interactive_menu
from memory import EpisodicMemory, SemanticMemory

logger = setup_logging(__name__)

MENU_OPTIONS = [
    "Browse episodic memories",
    "Search semantic memories",
    "Memory statistics",
    "Clear memories",
]


def browse_episodic(console: Console, episodic: EpisodicMemory) -> None:
    """Display all episodic memories in a Rich table."""
    entries = episodic.list_all()
    if not entries:
        console.print("[dim]No episodic memories found.[/dim]")
        return

    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("ID", style="dim", width=14)
    table.add_column("Date", style="cyan", width=19)
    table.add_column("Content", ratio=1)
    table.add_column("Imp.", style="yellow", width=5, justify="right")

    for entry in entries:
        date_str = entry.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
        content_preview = entry.content[:100].replace("\n", " ")
        if len(entry.content) > 100:
            content_preview += "..."
        table.add_row(entry.id, date_str, content_preview, f"{entry.importance:.1f}")

    console.print(Panel(table, title=f"Episodic Memories ({len(entries)})", border_style="cyan"))


def search_semantic(console: Console, semantic: SemanticMemory) -> None:
    """Search semantic memories and display results with similarity scores."""
    if semantic.collection.count() == 0:
        console.print("[dim]No semantic memories found.[/dim]")
        return

    console.print("[bold]Enter search query:[/bold] ", end="")
    try:
        query = input().strip()
    except EOFError:
        return

    if not query:
        return

    results = semantic.search(query, limit=10)
    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("#", style="dim", width=3)
    table.add_column("Similarity", style="green", width=12, justify="right")
    table.add_column("Content", ratio=1)
    table.add_column("Imp.", style="yellow", width=5, justify="right")

    for i, (entry, similarity) in enumerate(results, 1):
        content_preview = entry.content[:100].replace("\n", " ")
        if len(entry.content) > 100:
            content_preview += "..."
        table.add_row(str(i), f"{similarity:.3f}", content_preview, f"{entry.importance:.1f}")

    console.print(
        Panel(
            table,
            title=f'Semantic Search: "{query}" ({len(results)} results)',
            border_style="green",
        )
    )


def show_statistics(console: Console, episodic: EpisodicMemory, semantic: SemanticMemory) -> None:
    """Display memory statistics across tiers."""
    ep_stats = episodic.stats()
    sem_stats = semantic.stats()

    lines = [
        "[bold cyan]Episodic Memory[/bold cyan]",
        f"  Entries: {ep_stats['count']}",
        f"  File: {ep_stats['file']}",
    ]
    if ep_stats["oldest"]:
        lines.append(f"  Oldest: {ep_stats['oldest']}")
        lines.append(f"  Newest: {ep_stats['newest']}")

    lines.extend(
        [
            "",
            "[bold green]Semantic Memory[/bold green]",
            f"  Entries: {sem_stats['count']}",
            f"  Collection: {sem_stats['collection']}",
        ]
    )

    total = ep_stats["count"] + sem_stats["count"]
    lines.extend(["", f"[bold]Total persisted memories: {total}[/bold]"])

    console.print(Panel("\n".join(lines), title="Memory Statistics", border_style="blue"))


def clear_memories(console: Console, episodic: EpisodicMemory, semantic: SemanticMemory) -> None:
    """Clear memories with tier selection and confirmation."""
    clear_options = ["Episodic memories", "Semantic memories", "All memories"]
    choice = interactive_menu(console, clear_options, title="Select memories to clear")
    if not choice:
        return

    console.print(
        f"[yellow]Are you sure you want to clear {choice.lower()}? (y/N)[/yellow] ", end=""
    )
    try:
        confirm = input().strip().lower()
    except EOFError:
        return

    if confirm != "y":
        console.print("[dim]Cancelled.[/dim]")
        return

    if choice in ("Episodic memories", "All memories"):
        episodic.clear()
        console.print("[green]Episodic memories cleared.[/green]")
    if choice in ("Semantic memories", "All memories"):
        semantic.clear()
        console.print("[green]Semantic memories cleared.[/green]")


def main() -> None:
    """Run the memory inspector."""
    console = Console()

    episodic = EpisodicMemory()
    semantic = SemanticMemory()

    ep_count = episodic.stats()["count"]
    sem_count = semantic.stats()["count"]

    header = Panel(
        "[bold cyan]Memory Inspector[/bold cyan]\n\n"
        "Browse and manage persisted memories — no LLM calls required.\n\n"
        f"  Episodic: [cyan]{ep_count}[/cyan] entries\n"
        f"  Semantic: [green]{sem_count}[/green] entries",
        title="Tutorial 05 — Memory Inspector",
    )

    while True:
        choice = interactive_menu(console, MENU_OPTIONS, title="Memory Inspector", header=header)
        if not choice:
            break

        console.print()

        if choice == MENU_OPTIONS[0]:
            browse_episodic(console, episodic)
        elif choice == MENU_OPTIONS[1]:
            search_semantic(console, semantic)
        elif choice == MENU_OPTIONS[2]:
            show_statistics(console, episodic, semantic)
        elif choice == MENU_OPTIONS[3]:
            clear_memories(console, episodic, semantic)

        console.print("\n[dim]Press any key to continue...[/dim]")
        readchar.readkey()


if __name__ == "__main__":
    main()

"""Interactive arrow-key menu for selecting from a list of options."""

import readchar
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def interactive_menu(
    console: Console,
    items: list[str],
    title: str = "Select an Option",
    header: Panel | str | None = None,
    allow_custom: bool = False,
    custom_label: str = "✏️  Custom...",
    custom_prompt: str = "Enter your choice",
) -> str | None:
    """Display an interactive menu with arrow-key navigation.

    Returns the selected item string, or None if the user quits.
    """
    display_items = [*items, custom_label] if allow_custom else list(items)
    selected_idx = 0

    while True:
        console.clear()

        if header is not None:
            if isinstance(header, str):
                console.print(header)
            else:
                console.print(header)
            console.print()

        table = Table(show_header=False, show_edge=False, pad_edge=False, box=None)
        table.add_column("Item", style="cyan")
        for idx, item in enumerate(display_items):
            if idx == selected_idx:
                table.add_row(f"▶ {item}", style="bold green")
            else:
                table.add_row(f"  {item}")

        console.print(
            Panel(
                table,
                title=f"[bold cyan]{title}[/bold cyan]",
                border_style="blue",
                subtitle="[dim]↑↓: Navigate | Enter: Select | q: Quit[/dim]",
            )
        )

        key = readchar.readkey()

        if key == readchar.key.UP:
            selected_idx = (selected_idx - 1) % len(display_items)
        elif key == readchar.key.DOWN:
            selected_idx = (selected_idx + 1) % len(display_items)
        elif key == readchar.key.ENTER:
            if selected_idx < len(items):
                return items[selected_idx]
            # Custom option selected — prompt for free-text input
            console.print(f"\n[bold green]{custom_prompt}:[/bold green] ", end="")
            custom = input().strip()
            return custom if custom else None
        elif key in ("q", "Q"):
            return None

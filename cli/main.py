#!/usr/bin/env python3
"""Interactive menu for navigating and executing Python lessons."""

import os
import re
import select
import subprocess
import sys
import termios
import tomllib
from dataclasses import dataclass
from pathlib import Path

import readchar
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def readkey_with_esc_support() -> str:
    """Read a keypress with proper single-press ESC support.

    readchar.readkey() blocks after reading ESC (\\x1b) waiting for a second byte,
    since escape sequences (arrow keys, etc.) also start with \\x1b.
    This uses select() with a short timeout to distinguish standalone ESC.
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    term = termios.tcgetattr(fd)
    try:
        term[3] &= ~(termios.ICANON | termios.ECHO | termios.IGNBRK | termios.BRKINT)
        termios.tcsetattr(fd, termios.TCSAFLUSH, term)

        c1 = os.read(fd, 1).decode()
        if c1 != "\x1b":
            return c1

        # ESC received — wait briefly for more bytes (escape sequence)
        if not select.select([fd], [], [], 0.05)[0]:
            return "\x1b"  # standalone ESC

        c2 = os.read(fd, 1).decode()
        if c2 not in ("\x4f", "\x5b"):
            return c1 + c2

        c3 = os.read(fd, 1).decode()
        if c3 not in ("\x31", "\x32", "\x33", "\x35", "\x36"):
            return c1 + c2 + c3

        c4 = os.read(fd, 1).decode()
        if c4 not in ("\x30", "\x31", "\x33", "\x34", "\x35", "\x37", "\x38", "\x39"):
            return c1 + c2 + c3 + c4

        c5 = os.read(fd, 1).decode()
        return c1 + c2 + c3 + c4 + c5
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


@dataclass
class Script:
    """Represents a Python script in a lesson."""

    name: str
    path: Path


@dataclass
class Lesson:
    """Represents a lesson containing multiple scripts."""

    name: str
    path: Path
    scripts: list[Script]
    description: str = ""


@dataclass
class Module:
    """Represents a module containing multiple lessons."""

    name: str
    path: Path
    lessons: list[Lesson]


class InteractiveMenu:
    """Interactive menu for navigating modules, lessons, and scripts."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.console = Console()
        self.modules: list[Module] = []

    def get_lesson_description(self, lesson_path: Path) -> str:
        """Extract lesson description from pyproject.toml, removing 'Lesson N: ' prefix."""
        pyproject_path = lesson_path / "pyproject.toml"
        if not pyproject_path.exists():
            return ""

        try:
            with pyproject_path.open("rb") as f:
                data = tomllib.load(f)
                description = data.get("project", {}).get("description", "")

                # Remove "Lesson N: " or "Lesson NN: " prefix using regex
                description = re.sub(r"^Lesson\s+\d+:\s*", "", description)
                return description
        except Exception:
            return ""

    def discover_modules(self) -> None:
        """Discover all modules, lessons, and scripts in the base directory."""
        if not self.base_path.exists():
            self.console.print(
                f"[bold red]Error:[/bold red] Base directory not found: {self.base_path}"
            )
            return

        # Find all module directories matching pattern NN-* (e.g., 01-foundations, 02-advanced)
        module_dirs = sorted(
            [d for d in self.base_path.iterdir() if d.is_dir() and re.match(r"^\d{2}-", d.name)]
        )

        for module_dir in module_dirs:
            lessons = []

            # Find all lesson directories within the module
            lesson_dirs = sorted(
                [d for d in module_dir.iterdir() if d.is_dir() and d.name[0].isdigit()]
            )

            for lesson_dir in lesson_dirs:
                scripts = []

                # Find all Python scripts in the lesson
                script_files = sorted(
                    [
                        f
                        for f in lesson_dir.iterdir()
                        if f.suffix == ".py" and f.name != "__init__.py"
                    ]
                )

                for script_file in script_files:
                    scripts.append(Script(name=script_file.stem, path=script_file))

                if scripts:  # Only add lessons that have scripts
                    description = self.get_lesson_description(lesson_dir)
                    lessons.append(
                        Lesson(
                            name=lesson_dir.name,
                            path=lesson_dir,
                            scripts=scripts,
                            description=description,
                        )
                    )

            if lessons:  # Only add modules that have lessons
                self.modules.append(Module(name=module_dir.name, path=module_dir, lessons=lessons))

    def create_menu_panel(self, title: str, items: list[str], selected_idx: int) -> Panel:
        """Create a panel with menu items and highlight the selected one."""
        table = Table(show_header=False, show_edge=False, pad_edge=False, box=None)
        table.add_column("Item", style="cyan")

        for idx, item in enumerate(items):
            if idx == selected_idx:
                table.add_row(f"▶ {item}", style="bold green")
            else:
                table.add_row(f"  {item}")

        return Panel(
            table,
            title=f"[bold cyan]{title}[/bold cyan]",
            border_style="blue",
            subtitle="[dim]↑↓: Navigate | Enter: Select | q/ESC: Back/Quit[/dim]",
        )

    def show_module_menu(self) -> Module | None:
        """Display module selection menu and return selected module."""
        if not self.modules:
            self.console.print("[bold yellow]No modules found![/bold yellow]")
            return None

        selected_idx = 0
        module_names = [f"{m.name}" for m in self.modules]

        while True:
            self.console.clear()
            self.console.print(
                Panel(
                    "[bold magenta]Python Playground[/bold magenta]\n"
                    "[dim]Interactive Learning Environment[/dim]",
                    border_style="magenta",
                )
            )
            self.console.print()
            self.console.print(self.create_menu_panel("Select Module", module_names, selected_idx))

            key = readkey_with_esc_support()

            if key == readchar.key.UP:
                selected_idx = (selected_idx - 1) % len(module_names)
            elif key == readchar.key.DOWN:
                selected_idx = (selected_idx + 1) % len(module_names)
            elif key == readchar.key.ENTER:
                return self.modules[selected_idx]
            elif key in ("\x1b", "q", "Q"):
                return None

    def show_lesson_menu(self, module: Module) -> Lesson | None:
        """Display lesson selection menu and return selected lesson."""
        if not module.lessons:
            self.console.print("[bold yellow]No lessons found in this module![/bold yellow]")
            return None

        selected_idx = 0
        lesson_names = [lesson.name for lesson in module.lessons]

        while True:
            self.console.clear()
            self.console.print(
                Panel(
                    f"[bold magenta]Module: {module.name}[/bold magenta]",
                    border_style="magenta",
                )
            )
            self.console.print()
            self.console.print(self.create_menu_panel("Select Lesson", lesson_names, selected_idx))

            key = readkey_with_esc_support()

            if key == readchar.key.UP:
                selected_idx = (selected_idx - 1) % len(lesson_names)
            elif key == readchar.key.DOWN:
                selected_idx = (selected_idx + 1) % len(lesson_names)
            elif key == readchar.key.ENTER:
                return module.lessons[selected_idx]
            elif key in ("\x1b", "q", "Q"):
                return None

    def show_script_menu(self, module: Module, lesson: Lesson) -> Script | None:
        """Display script selection menu and return selected script."""
        if not lesson.scripts:
            self.console.print("[bold yellow]No scripts found in this lesson![/bold yellow]")
            return None

        selected_idx = 0
        script_names = [f"{s.name}.py" for s in lesson.scripts]

        while True:
            self.console.clear()
            # Build context panel content
            context_content = (
                f"[bold magenta]Module: {module.name}[/bold magenta]\n"
                f"[bold magenta]Lesson: {lesson.name}[/bold magenta]"
            )
            if lesson.description:
                context_content += f"\n[dim]{lesson.description}[/dim]"

            self.console.print(Panel(context_content, border_style="magenta"))
            self.console.print()
            self.console.print(self.create_menu_panel("Select Script", script_names, selected_idx))

            key = readkey_with_esc_support()

            if key == readchar.key.UP:
                selected_idx = (selected_idx - 1) % len(script_names)
            elif key == readchar.key.DOWN:
                selected_idx = (selected_idx + 1) % len(script_names)
            elif key == readchar.key.ENTER:
                return lesson.scripts[selected_idx]
            elif key in ("\x1b", "q", "Q"):
                return None

    def execute_script(self, script: Script, lesson: Lesson) -> None:
        """Execute a Python script and display the output."""
        self.console.clear()
        self.console.print(
            Panel(
                f"[bold green]Executing: {script.name}.py[/bold green]",
                border_style="green",
            )
        )
        self.console.print()

        try:
            # Change to the lesson directory to ensure proper context
            original_cwd = Path.cwd()
            os.chdir(lesson.path)

            # Create a clean environment without VIRTUAL_ENV to avoid uv warnings
            env = os.environ.copy()
            env.pop("VIRTUAL_ENV", None)

            # Execute the script using uv run to ensure dependencies are available
            result = subprocess.run(
                ["uv", "run", "python", script.path.name],
                capture_output=False,  # Show output in real-time
                text=True,
                env=env,
            )

            # Change back to original directory
            os.chdir(original_cwd)

            self.console.print()
            if result.returncode == 0:
                self.console.print(
                    Panel(
                        "[bold green]✓ Script executed successfully![/bold green]",
                        border_style="green",
                    )
                )
            else:
                self.console.print(
                    Panel(
                        f"[bold red]✗ Script exited with code {result.returncode}[/bold red]",
                        border_style="red",
                    )
                )

        except FileNotFoundError:
            self.console.print(
                Panel(
                    "[bold red]Error: 'uv' not found. Please install uv first.[/bold red]",
                    border_style="red",
                )
            )
        except Exception as e:
            self.console.print(
                Panel(
                    f"[bold red]Error executing script: {e}[/bold red]",
                    border_style="red",
                )
            )

        self.console.print()
        self.console.print("[dim]Press any key to return to menu...[/dim]")
        readchar.readkey()

    def run(self) -> None:
        """Run the interactive menu system."""
        self.console.print("[bold cyan]Discovering modules, lessons, and scripts...[/bold cyan]")
        self.discover_modules()

        if not self.modules:
            self.console.print("[bold red]No modules found! Exiting.[/bold red]")
            return

        while True:
            # Show module menu
            module = self.show_module_menu()
            if module is None:
                self.console.clear()
                self.console.print("[bold cyan]Goodbye! Happy learning! 👋[/bold cyan]")
                break

            while True:
                # Show lesson menu
                lesson = self.show_lesson_menu(module)
                if lesson is None:
                    break  # Go back to module menu

                while True:
                    # Show script menu
                    script = self.show_script_menu(module, lesson)
                    if script is None:
                        break  # Go back to lesson menu

                    # Execute the selected script
                    self.execute_script(script, lesson)


def main() -> None:
    """Main entry point for the interactive menu."""
    try:
        # Get project root (parent of cli package directory)
        base_path = Path(__file__).parent.parent
        menu = InteractiveMenu(base_path)
        menu.run()
    except KeyboardInterrupt:
        console = Console()
        console.clear()
        console.print("\n[bold cyan]Goodbye! Happy learning! 👋[/bold cyan]")
        sys.exit(0)


if __name__ == "__main__":
    main()

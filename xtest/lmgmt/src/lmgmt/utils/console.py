"""Rich console helpers for formatted output."""

from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.style import Style
from rich.table import Table

# Global console instance
console = Console()

# Status styles
STYLE_SUCCESS = Style(color="green", bold=True)
STYLE_ERROR = Style(color="red", bold=True)
STYLE_WARNING = Style(color="yellow")
STYLE_INFO = Style(color="blue")
STYLE_DIM = Style(dim=True)


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]![/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[blue]ℹ[/blue] {message}")


def print_header(title: str) -> None:
    """Print a section header."""
    console.print(Panel(title, style="bold cyan", expand=False))


@contextmanager
def status_spinner(message: str) -> Iterator[None]:
    """Context manager for showing a spinner during operations."""
    with console.status(f"[bold blue]{message}[/bold blue]"):
        yield


def create_service_table() -> Table:
    """Create a table for displaying service status."""
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Service", style="cyan", no_wrap=True)
    table.add_column("Port", justify="right")
    table.add_column("Type", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Health", justify="center")
    return table


def format_status(running: bool) -> str:
    """Format a running status indicator."""
    if running:
        return "[green]●[/green] running"
    return "[red]○[/red] stopped"


def format_health(healthy: bool | None) -> str:
    """Format a health status indicator."""
    if healthy is None:
        return "[dim]—[/dim]"
    if healthy:
        return "[green]✓[/green]"
    return "[red]✗[/red]"


def create_progress() -> Progress:
    """Create a progress display for multi-step operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    )

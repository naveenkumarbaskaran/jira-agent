"""
CLI for viz-agent.

Usage
-----
    viz-agent chart data.csv "show monthly revenue as a bar chart grouped by region" \
        --output chart.html
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()


@click.group()
def cli() -> None:
    """viz-agent — turn natural language into Plotly charts."""


@cli.command()
@click.argument("csv", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("description")
@click.option(
    "--output",
    "-o",
    default="chart.html",
    show_default=True,
    help="Output file path.  Extension determines format: .html, .png, .svg, .pdf.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Print tool calls and intermediate messages.",
)
@click.option(
    "--show-code",
    "-s",
    is_flag=True,
    default=False,
    help="Print the generated Python code to the terminal.",
)
def chart(
    csv: Path,
    description: str,
    output: str,
    verbose: bool,
    show_code: bool,
) -> None:
    """
    Generate a Plotly chart from a CSV file and a plain-English DESCRIPTION.

    CSV      Path to the input CSV file.

    DESCRIPTION  Natural-language chart request, e.g.
                 "show monthly revenue as a bar chart grouped by region"
    """
    from viz_agent.agent import VizAgent
    from viz_agent.executor import CodeExecutor, ExecutionError

    console.print(
        Panel(
            f"[bold]CSV[/bold]: {csv}\n"
            f"[bold]Description[/bold]: {description}\n"
            f"[bold]Output[/bold]: {output}",
            title="[bold blue]viz-agent[/bold blue]",
            expand=False,
        )
    )

    console.print("\n[bold yellow]Asking Claude to generate chart code...[/bold yellow]")
    agent = VizAgent()

    try:
        code, explanation = agent.generate_chart_code(
            csv, description, verbose=verbose
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bold red]Error generating code:[/bold red] {exc}")
        sys.exit(1)

    if show_code:
        console.print()
        console.print(
            Panel(
                Syntax(code, "python", theme="monokai", line_numbers=True),
                title="[bold green]Generated code[/bold green]",
                expand=False,
            )
        )

    if explanation:
        console.print(f"\n[dim]{explanation}[/dim]")

    console.print("\n[bold yellow]Executing and saving chart...[/bold yellow]")
    executor = CodeExecutor(csv)

    try:
        saved = executor.save(code, output)
    except ExecutionError as exc:
        console.print(f"[bold red]Execution error:[/bold red] {exc}")
        if verbose:
            console.print_exception()
        sys.exit(1)
    except RuntimeError as exc:
        console.print(f"[bold red]Save error:[/bold red] {exc}")
        sys.exit(1)

    console.print(
        f"\n[bold green]Chart saved to:[/bold green] {saved}"
    )


def main() -> None:
    cli()


if __name__ == "__main__":
    main()

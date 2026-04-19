#!/usr/bin/env python3
"""
CLI entrypoint for the code review agent.

Usage:
  python main.py review path/to/file.py
  python main.py review path/to/directory/
  python main.py review path/to/file.py --no-stream --output report.md
"""

import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

load_dotenv()

console = Console()


@click.group()
def cli():
    """AI Code Review Agent — dual senior DE + appsec perspective."""


@cli.command()
@click.argument("target", type=click.Path(exists=True))
@click.option("--no-stream", is_flag=True, default=False, help="Disable streaming output")
@click.option("--output", "-o", type=click.Path(), default=None, help="Save review to a markdown file")
@click.option("--provider", "-p", default="anthropic", show_default=True,
              help="LLM provider to use: anthropic, gemini, groq")
@click.option("--api-key", default=None, help="API key (overrides environment variable)")
@click.option("--smart", is_flag=True, default=False,
              help="Smart mode: skip tests, strip comments, prioritise high-risk files. ~40% fewer tokens.")
@click.option("--diff", "diff_ref", default=None,
              help="Review only changes vs a git ref. e.g. --diff HEAD~1 or --diff main")
def review(target: str, no_stream: bool, output: str | None, provider: str, api_key: str | None, smart: bool, diff_ref: str | None):
    """Review a file or directory."""
    from agent.reviewer import review_target
    from agent.parser import parse_review
    from agent.providers.factory import available_providers

    if provider not in available_providers():
        console.print(f"[red]Unknown provider '{provider}'. Choose from: {', '.join(available_providers())}[/]")
        sys.exit(1)

    target_path = Path(target).resolve()
    if diff_ref:
        mode_label = f"diff vs {diff_ref}"
    elif smart:
        mode_label = "smart (comments stripped, tests skipped)"
    else:
        mode_label = "full"
    console.print(Panel(
        f"[bold cyan]Reviewing:[/] {target_path}\n[dim]Provider: {provider} | Mode: {mode_label}[/]",
        expand=False,
    ))

    if no_stream:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as progress:
            progress.add_task("Running review...", total=None)
            result_text = review_target(str(target_path), stream=False, provider_name=provider, api_key=api_key, smart=smart, diff_ref=diff_ref)

        _display_result(result_text, output)
    else:
        result_text = _stream_review(target_path, output, provider, api_key, smart, diff_ref)

    if output:
        console.print(f"\n[green]Report saved to:[/] {output}")


def _stream_review(target_path: Path, output: str | None, provider: str = "anthropic", api_key: str | None = None, smart: bool = False, diff_ref: str | None = None) -> str:
    from agent.reviewer import review_target

    full_text = ""
    current_chunk = 0
    total_chunks = 0

    console.print()
    for chunk_idx, total, delta in review_target(str(target_path), stream=True, provider_name=provider, api_key=api_key, smart=smart, diff_ref=diff_ref):
        if total != total_chunks:
            total_chunks = total
        if chunk_idx != current_chunk:
            current_chunk = chunk_idx
            if total_chunks > 1:
                console.print(f"\n[dim]--- Chunk {chunk_idx + 1}/{total_chunks} ---[/]\n")
        console.print(delta, end="", highlight=False)
        full_text += delta

    console.print("\n")

    if output:
        Path(output).write_text(full_text, encoding="utf-8")

    return full_text


def _display_result(result_text: str, output: str | None):
    from agent.parser import parse_review, SEVERITY_COLORS, VERDICT_COLORS

    parsed = parse_review(result_text)

    if parsed.verdict:
        color = VERDICT_COLORS.get(parsed.verdict, "white")
        console.print(Panel(
            f"[bold]{parsed.verdict.value}[/]",
            title="VERDICT",
            border_style=_rich_color(color),
            expand=False,
        ))

    if parsed.summary:
        console.print(Panel(parsed.summary, title="SUMMARY", border_style="cyan"))

    if parsed.findings:
        console.print(f"\n[bold]FINDINGS ({len(parsed.findings)})[/]\n")
        for f in parsed.findings_by_severity:
            color = _rich_color(SEVERITY_COLORS.get(f.severity, "#ffffff"))
            header = f"[{color}][{f.severity.value}][/] [{f.category}]"
            if f.file:
                header += f" — {f.file}"
                if f.line:
                    header += f":{f.line}"
            console.print(header)
            if f.problem:
                console.print(f"  [bold]Problem:[/] {f.problem}")
            if f.impact:
                console.print(f"  [bold]Impact:[/]  {f.impact}")
            if f.fix:
                console.print(f"  [bold]Fix:[/]     {f.fix}")
            console.print()
    else:
        console.print(Markdown(result_text))

    if output:
        Path(output).write_text(result_text, encoding="utf-8")


def _rich_color(hex_color: str) -> str:
    color_map = {
        "#FF4B4B": "red",
        "#FF8C00": "dark_orange",
        "#FFC107": "yellow",
        "#4CAF50": "green",
        "#2196F3": "blue",
        "#8BC34A": "chartreuse3",
    }
    return color_map.get(hex_color, "white")


if __name__ == "__main__":
    cli()

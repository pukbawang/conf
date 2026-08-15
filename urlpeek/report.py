"""Formats the fetch/render/checks results into a terminal report."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .checks import Flag, risk_level
from .fetcher import FetchResult
from .render import RenderResult

RISK_STYLE = {
    "NONE": "bold green",
    "LOW": "bold cyan",
    "MEDIUM": "bold yellow",
    "HIGH": "bold red",
}

SEVERITY_ICON = {"info": "[cyan]i[/cyan]", "warn": "[yellow]![/yellow]", "danger": "[red]X[/red]"}


def print_report(
    fetch: FetchResult,
    render: RenderResult | None,
    flags: list[Flag],
    console: Console | None = None,
) -> None:
    console = console or Console()
    risk = risk_level(flags)

    console.print(Panel.fit(f"urlpeek preview — {fetch.input_url}", style="bold"))

    if fetch.error:
        console.print(f"[bold red]Failed to fetch this URL:[/bold red] {fetch.error}")
        return

    overview = Table(show_header=False, box=None, pad_edge=False)
    overview.add_row("Final URL", fetch.final_url or "-")
    overview.add_row("Status", str(fetch.status_code))
    overview.add_row("Content-Type", fetch.content_type or "-")
    if fetch.title:
        overview.add_row("Title", fetch.title)
    if fetch.description:
        overview.add_row("Description", fetch.description)
    console.print(overview)

    if fetch.redirect_chain:
        console.print(f"\n[bold]Redirect chain[/bold] ({len(fetch.redirect_chain)} hop(s)):")
        for i, hop in enumerate(fetch.redirect_chain, 1):
            console.print(f"  {i}. [{hop.status_code}] {hop.url}")
        console.print(f"  -> {fetch.final_url}")

    if fetch.tls:
        console.print("\n[bold]TLS certificate[/bold]")
        if fetch.tls.error:
            console.print(f"  [red]{fetch.tls.error}[/red]")
        else:
            console.print(f"  Subject: {fetch.tls.subject}")
            console.print(f"  Issuer:  {fetch.tls.issuer}")
            console.print(f"  Valid until: {fetch.tls.not_after}")

    if render and render.third_party_domains:
        console.print(f"\n[bold]Network activity during render[/bold]")
        console.print(f"  Requests touched {len(render.third_party_domains)} distinct domain(s):")
        for host in sorted(render.third_party_domains)[:20]:
            console.print(f"    - {host}")
        if len(render.third_party_domains) > 20:
            console.print(f"    ... and {len(render.third_party_domains) - 20} more")

    console.print("\n[bold]Security flags[/bold]")
    if flags:
        for f in flags:
            console.print(f"  {SEVERITY_ICON[f.severity]} {f.message}")
    else:
        console.print("  [green]No suspicious indicators found by these heuristic checks.[/green]")

    console.print(
        f"\n[bold]Heuristic risk level:[/bold] [{RISK_STYLE[risk]}]{risk}[/{RISK_STYLE[risk]}]"
        " [dim](signals only, not a verdict — always use your judgement)[/dim]"
    )

    if render and render.screenshot_path:
        console.print(f"\nScreenshot saved to: {render.screenshot_path}")
    elif render and render.error:
        console.print(f"\n[dim]Screenshot unavailable: {render.error}[/dim]")

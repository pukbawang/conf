from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from rich.console import Console

from .checks import run_checks
from .fetcher import fetch_metadata
from .render import render_preview
from .report import print_report


def _normalize_url(raw: str) -> str:
    if not re.match(r"^\w+://", raw):
        return f"https://{raw}"
    return raw


def _screenshot_path(out_dir: Path, url: str) -> str:
    host = urlparse(url).hostname or "unknown-host"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_host = re.sub(r"[^a-zA-Z0-9.-]", "_", host)
    out_dir.mkdir(parents=True, exist_ok=True)
    return str(out_dir / f"{stamp}_{safe_host}.png")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="urlpeek",
        description="Preview what's at a URL — metadata, redirects, TLS, and a sandboxed "
        "screenshot — before opening it in your real browser.",
    )
    parser.add_argument("url", help="URL to preview (scheme optional, defaults to https://)")
    parser.add_argument("--timeout", type=int, default=10, help="Network timeout in seconds (default: 10)")
    parser.add_argument("--no-screenshot", action="store_true", help="Skip the sandboxed screenshot step")
    parser.add_argument("--full-page", action="store_true", help="Capture the full scrollable page, not just the viewport")
    parser.add_argument("--out-dir", default="previews", help="Directory to save screenshots to (default: previews/)")
    args = parser.parse_args(argv)

    console = Console()
    url = _normalize_url(args.url.strip())

    with console.status("Fetching metadata..."):
        fetch = fetch_metadata(url, timeout=args.timeout)

    render = None
    if not args.no_screenshot and not fetch.error:
        out_path = _screenshot_path(Path(args.out_dir), fetch.final_url or url)
        with console.status("Rendering sandboxed screenshot..."):
            render = render_preview(fetch.final_url or url, out_path, timeout_ms=args.timeout * 1000, full_page=args.full_page)

    flags = run_checks(fetch, render)
    print_report(fetch, render, flags, console=console)

    return 0 if not fetch.error else 1


if __name__ == "__main__":
    sys.exit(main())

# urlpeek

Preview what's at a URL before you open it in your real browser.

`urlpeek` never opens the URL in a browser you actually use. Instead it:

1. Fetches the URL over plain HTTP(S) (no JavaScript, no rendering) and reports
   the redirect chain, final destination, response headers, TLS certificate
   details, and page title/description.
2. Runs a set of heuristic checks for common phishing/malware red flags:
   IP-literal hosts, punycode domains, `@`-obfuscated URLs, known shorteners,
   abused TLDs, cross-domain redirects, expired/invalid TLS certs, password
   fields served over plain HTTP, and more.
3. Optionally renders the page in a disposable, sandboxed headless Chromium
   context (no persistent storage, no permissions granted, downloads
   blocked, dialogs auto-dismissed) purely to take a screenshot, and reports
   which third-party domains it talked to while loading.

This gives you a look at a page's content and behavior without ever letting
it touch your everyday browser profile, cookies, or extensions.

**Note:** the screenshot step does execute the page's JavaScript inside the
sandboxed browser context. Everything about that context is thrown away
after each run. If you don't want that at all, use `--no-screenshot` for a
metadata-only, JS-free check.

## Install

```bash
pip install -e .
playwright install chromium   # only needed if Chromium isn't already available
```

## Usage

```bash
urlpeek example.com
urlpeek https://bit.ly/something --full-page
urlpeek suspicious-link.example --no-screenshot
```

Options:

- `--timeout SECONDS` — network timeout (default: 10)
- `--no-screenshot` — skip the sandboxed render/screenshot step
- `--full-page` — capture the full scrollable page instead of just the viewport
- `--out-dir DIR` — where screenshots are saved (default: `previews/`)

## Output

A terminal report with the resolved URL, redirect chain, TLS info, page
metadata, a list of triggered security flags, an overall heuristic risk
level (`NONE` / `LOW` / `MEDIUM` / `HIGH`), and the path to the saved
screenshot.

The risk level is a heuristic signal, not a verdict — always use your own
judgement, and when in doubt don't visit the real thing either.

"""Heuristic suspicious-indicator checks. These are signals, not a verdict."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

from .fetcher import FetchResult
from .render import RenderResult

SEVERITY_ORDER = {"info": 0, "warn": 1, "danger": 2}

KNOWN_SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
    "rebrand.ly", "cutt.ly", "shorturl.at", "rb.gy", "s.id", "tiny.cc",
    "bl.ink", "snip.ly", "lnkd.in",
}

SUSPICIOUS_TLDS = {
    "zip", "mov", "top", "work", "click", "link", "gq", "tk", "ml", "cf",
    "xyz", "country", "kim", "science", "party", "review",
}


@dataclass
class Flag:
    severity: str  # info | warn | danger
    message: str


def _hostname_is_ip(hostname: str | None) -> bool:
    if not hostname:
        return False
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def _registrable_guess(hostname: str) -> str:
    """Very rough eTLD+1 guess (last two labels). Good enough for a same-vs-different check."""
    parts = hostname.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else hostname


def run_checks(fetch: FetchResult, render: RenderResult | None) -> list[Flag]:
    flags: list[Flag] = []

    input_parsed = urlparse(fetch.input_url)
    input_host = (input_parsed.hostname or "").lower()

    if "@" in fetch.input_url.split("://", 1)[-1].split("/", 1)[0]:
        flags.append(Flag("danger", "URL contains '@' before the host — a classic trick to disguise the real destination."))

    if _hostname_is_ip(input_host):
        flags.append(Flag("warn", f"URL uses a raw IP address ({input_host}) instead of a domain name."))

    if input_host.startswith("xn--") or ".xn--" in input_host:
        flags.append(Flag("warn", "Domain uses punycode (xn--) — often used for lookalike/homograph domains."))

    if input_host in KNOWN_SHORTENERS:
        flags.append(Flag("info", f"'{input_host}' is a known URL shortener — the resolved destination is shown above."))

    tld = input_host.rsplit(".", 1)[-1] if "." in input_host else ""
    if tld in SUSPICIOUS_TLDS:
        flags.append(Flag("info", f"TLD '.{tld}' is frequently abused for phishing/malware (not proof of anything by itself)."))

    if input_parsed.port and input_parsed.port not in (80, 443):
        flags.append(Flag("warn", f"URL uses a non-standard port ({input_parsed.port})."))

    if input_parsed.scheme == "http":
        flags.append(Flag("warn", "Connection is plain HTTP, not HTTPS — traffic is unencrypted."))

    if fetch.error:
        flags.append(Flag("danger", f"Could not fetch the URL: {fetch.error}"))
        return flags

    if len(fetch.redirect_chain) > 3:
        flags.append(Flag("warn", f"URL redirected {len(fetch.redirect_chain)} times before landing."))

    if fetch.final_url:
        final_host = (urlparse(fetch.final_url).hostname or "").lower()
        if final_host and input_host and _registrable_guess(final_host) != _registrable_guess(input_host):
            flags.append(Flag(
                "warn",
                f"Redirects to a different domain than requested: {input_host} -> {final_host}.",
            ))

    if fetch.tls:
        if fetch.tls.error:
            flags.append(Flag("danger", f"TLS certificate problem: {fetch.tls.error}"))
        elif fetch.tls.expired:
            flags.append(Flag("danger", f"TLS certificate is expired (valid until {fetch.tls.not_after})."))

    if fetch.has_password_field and input_parsed.scheme != "https":
        flags.append(Flag("danger", "Page appears to contain a password field but is not served over HTTPS."))

    if render and render.error:
        flags.append(Flag("info", f"Could not render a screenshot: {render.error}"))

    if render and render.final_url and fetch.final_url and render.final_url != fetch.final_url:
        flags.append(Flag(
            "warn",
            f"Page navigated client-side (via JavaScript) to a different URL after load: {render.final_url}",
        ))

    if render and len(render.third_party_domains) > 15:
        flags.append(Flag(
            "info",
            f"Page loaded resources from {len(render.third_party_domains)} distinct domains while rendering.",
        ))

    if render and render.downloads_blocked:
        flags.append(Flag("warn", "Page attempted to trigger a file download during load — this was blocked."))

    flags.sort(key=lambda f: SEVERITY_ORDER[f.severity], reverse=True)
    return flags


def risk_level(flags: list[Flag]) -> str:
    if any(f.severity == "danger" for f in flags):
        return "HIGH"
    if any(f.severity == "warn" for f in flags):
        return "MEDIUM"
    if flags:
        return "LOW"
    return "NONE"

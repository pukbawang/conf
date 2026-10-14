"""Fetches URL metadata over plain HTTP(S) without ever rendering the page."""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "urlpeek/0.1 (safety preview tool; not a browser)"
DEFAULT_TIMEOUT = 10


@dataclass
class RedirectHop:
    url: str
    status_code: int


@dataclass
class TlsInfo:
    subject: str | None = None
    issuer: str | None = None
    not_before: str | None = None
    not_after: str | None = None
    expired: bool | None = None
    error: str | None = None


@dataclass
class FetchResult:
    input_url: str
    final_url: str | None = None
    redirect_chain: list[RedirectHop] = field(default_factory=list)
    status_code: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    content_type: str | None = None
    title: str | None = None
    description: str | None = None
    has_password_field: bool = False
    tls: TlsInfo | None = None
    error: str | None = None


def _get_tls_info(hostname: str, port: int = 443, timeout: int = DEFAULT_TIMEOUT) -> TlsInfo:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as tls_sock:
                cert = tls_sock.getpeercert()
    except Exception as exc:  # noqa: BLE001 - report any TLS failure, don't crash the preview
        return TlsInfo(error=str(exc))

    def _name(parts) -> str | None:
        if not parts:
            return None
        flat = [item for rdn in parts for item in rdn]
        common_name = next((v for k, v in flat if k == "commonName"), None)
        return common_name or ", ".join(f"{k}={v}" for k, v in flat)

    not_after = cert.get("notAfter")
    expired = None
    not_after_str = None
    if not_after:
        try:
            expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            expired = expiry < datetime.now(timezone.utc)
            not_after_str = expiry.isoformat()
        except ValueError:
            not_after_str = not_after

    return TlsInfo(
        subject=_name(cert.get("subject")),
        issuer=_name(cert.get("issuer")),
        not_before=cert.get("notBefore"),
        not_after=not_after_str,
        expired=expired,
    )


def fetch_metadata(url: str, timeout: int = DEFAULT_TIMEOUT) -> FetchResult:
    result = FetchResult(input_url=url)

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
    except requests.RequestException as exc:
        result.error = str(exc)
        return result

    result.final_url = resp.url
    result.status_code = resp.status_code
    result.headers = dict(resp.headers)
    result.content_type = resp.headers.get("Content-Type")
    result.redirect_chain = [RedirectHop(url=r.url, status_code=r.status_code) for r in resp.history]

    if result.content_type and "html" in result.content_type.lower():
        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            if soup.title and soup.title.string:
                result.title = soup.title.string.strip()
            desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
                "meta", attrs={"property": "og:description"}
            )
            if desc_tag and desc_tag.get("content"):
                result.description = desc_tag["content"].strip()
            result.has_password_field = soup.find("input", attrs={"type": "password"}) is not None
        except Exception:  # noqa: BLE001 - metadata extraction is best-effort
            pass

    parsed_final = urlparse(result.final_url)
    if parsed_final.scheme == "https":
        port = parsed_final.port or 443
        result.tls = _get_tls_info(parsed_final.hostname, port, timeout=timeout)

    return result

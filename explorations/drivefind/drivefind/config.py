"""Central place for the environment variables and paths drivefind needs."""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DRIVEFIND_DATA_DIR", Path.home() / ".drivefind"))

CLIENT_SECRETS_FILE = Path(os.environ.get("DRIVEFIND_CLIENT_SECRETS", DATA_DIR / "client_secret.json"))
TOKEN_FILE = Path(os.environ.get("DRIVEFIND_TOKEN_FILE", DATA_DIR / "token.json"))
DB_PATH = Path(os.environ.get("DRIVEFIND_DB", DATA_DIR / "drivefind.sqlite3"))

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("DRIVEFIND_ANTHROPIC_MODEL", "claude-sonnet-5-5")

VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")
VOYAGE_MODEL = os.environ.get("DRIVEFIND_VOYAGE_MODEL", "voyage-3.5")

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

MAX_EXTRACT_CHARS = int(os.environ.get("DRIVEFIND_MAX_EXTRACT_CHARS", "20000"))


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

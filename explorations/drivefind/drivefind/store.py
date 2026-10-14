"""SQLite-backed record + vector store.

Small enough drives don't need a real vector database — embeddings are
stored as JSON and compared with cosine similarity in Python at search
time. Swap this out for something like sqlite-vec or a hosted vector DB if
a drive grows past a few tens of thousands of files.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from . import config
from .ai_provider import AIRecord
from .drive_client import DriveFile

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size INTEGER,
    modified_time TEXT,
    web_view_link TEXT,
    change_token TEXT,
    description TEXT,
    tags TEXT,
    subtitle TEXT,
    embedding TEXT,
    manual_override INTEGER NOT NULL DEFAULT 0,
    indexed_at TEXT
);
"""


@dataclass
class FileRecord:
    id: str
    name: str
    mime_type: str
    size: int | None
    modified_time: str | None
    web_view_link: str | None
    change_token: str | None
    description: str | None
    tags: list[str]
    subtitle: str | None
    manual_override: bool
    indexed_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "FileRecord":
        return cls(
            id=row["id"],
            name=row["name"],
            mime_type=row["mime_type"],
            size=row["size"],
            modified_time=row["modified_time"],
            web_view_link=row["web_view_link"],
            change_token=row["change_token"],
            description=row["description"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            subtitle=row["subtitle"],
            manual_override=bool(row["manual_override"]),
            indexed_at=row["indexed_at"],
        )


def connect() -> sqlite3.Connection:
    config.ensure_data_dir()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def needs_reindex(conn: sqlite3.Connection, file: DriveFile) -> bool:
    """A manual edit (manual_override) only protects a record while the file
    itself is unchanged — an actual change to the file always wins."""
    row = conn.execute("SELECT change_token FROM files WHERE id = ?", (file.id,)).fetchone()
    if row is None:
        return True
    return row["change_token"] != file.change_token


def upsert_file(conn: sqlite3.Connection, file: DriveFile, record: AIRecord, embedding: list[float]) -> None:
    conn.execute(
        """
        INSERT INTO files (id, name, mime_type, size, modified_time, web_view_link,
                            change_token, description, tags, subtitle, embedding,
                            manual_override, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, mime_type=excluded.mime_type, size=excluded.size,
            modified_time=excluded.modified_time, web_view_link=excluded.web_view_link,
            change_token=excluded.change_token, description=excluded.description,
            tags=excluded.tags, subtitle=excluded.subtitle, embedding=excluded.embedding,
            manual_override=0, indexed_at=excluded.indexed_at
        """,
        (
            file.id,
            file.name,
            file.mime_type,
            file.size,
            file.modified_time,
            file.web_view_link,
            file.change_token,
            record.description,
            json.dumps(record.tags),
            record.subtitle,
            json.dumps(embedding),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def update_record(
    conn: sqlite3.Connection,
    file_id: str,
    *,
    description: str | None = None,
    tags: list[str] | None = None,
    subtitle: str | None = None,
    embedding: list[float] | None = None,
) -> None:
    fields, values = [], []
    if description is not None:
        fields.append("description = ?")
        values.append(description)
    if tags is not None:
        fields.append("tags = ?")
        values.append(json.dumps(tags))
    if subtitle is not None:
        fields.append("subtitle = ?")
        values.append(subtitle)
    if embedding is not None:
        fields.append("embedding = ?")
        values.append(json.dumps(embedding))
    if not fields:
        return
    fields.append("manual_override = 1")
    values.append(file_id)
    conn.execute(f"UPDATE files SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()


def get_file(conn: sqlite3.Connection, file_id: str) -> FileRecord | None:
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    return FileRecord.from_row(row) if row else None


def list_files(conn: sqlite3.Connection) -> list[FileRecord]:
    rows = conn.execute("SELECT * FROM files ORDER BY indexed_at DESC").fetchall()
    return [FileRecord.from_row(r) for r in rows]


def search(conn: sqlite3.Connection, query_embedding: list[float], top_k: int = 10) -> list[tuple[FileRecord, float]]:
    rows = conn.execute("SELECT * FROM files WHERE embedding IS NOT NULL").fetchall()
    if not rows:
        return []

    query_vec = np.array(query_embedding, dtype=np.float64)
    query_norm = np.linalg.norm(query_vec)

    scored: list[tuple[FileRecord, float]] = []
    for row in rows:
        vec = np.array(json.loads(row["embedding"]), dtype=np.float64)
        denom = query_norm * np.linalg.norm(vec)
        score = float(np.dot(query_vec, vec) / denom) if denom else 0.0
        scored.append((FileRecord.from_row(row), score))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_k]

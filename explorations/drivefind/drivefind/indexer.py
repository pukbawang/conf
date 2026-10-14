"""Orchestrates the index pipeline: Drive listing -> extract -> AI record -> embed -> store."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable

from . import store
from .ai_provider import AIRecordProvider
from .drive_client import DriveClient, DriveFile
from .embedding_provider import EmbeddingProvider
from .extract import extract_text

ProgressCallback = Callable[[str, DriveFile], None]


@dataclass
class IndexSummary:
    scanned: int = 0
    indexed: int = 0
    skipped_unchanged: int = 0
    failed: int = 0


def searchable_text(name: str, subtitle: str, description: str, tags: list[str]) -> str:
    return "\n".join([name, subtitle, description, ", ".join(tags)])


def run_index(
    conn: sqlite3.Connection,
    drive: DriveClient,
    ai_provider: AIRecordProvider,
    embedding_provider: EmbeddingProvider,
    on_progress: ProgressCallback | None = None,
) -> IndexSummary:
    summary = IndexSummary()

    for file in drive.list_files():
        summary.scanned += 1

        if not store.needs_reindex(conn, file):
            summary.skipped_unchanged += 1
            if on_progress:
                on_progress("skipped", file)
            continue

        try:
            text = None
            try:
                content, effective_mime = drive.fetch_bytes(file)
                text = extract_text(content, effective_mime)
            except Exception:
                pass  # some files (shortcuts, restricted, huge) just won't download — fall back to metadata only

            record = ai_provider.generate(file.name, file.mime_type, text)
            embedding = embedding_provider.embed_one(
                searchable_text(file.name, record.subtitle, record.description, record.tags)
            )
            store.upsert_file(conn, file, record, embedding)
            summary.indexed += 1
            if on_progress:
                on_progress("indexed", file)
        except Exception:
            summary.failed += 1
            if on_progress:
                on_progress("failed", file)

    return summary

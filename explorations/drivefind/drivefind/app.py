"""FastAPI app: trigger indexing, run semantic search, edit records, download files."""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from . import config, store
from .ai_provider import AIRecordProvider, AnthropicRecordProvider, FakeAIRecordProvider
from .drive_client import DriveClient, DriveFile
from .embedding_provider import EmbeddingProvider, FakeEmbeddingProvider, VoyageEmbeddingProvider
from .indexer import run_index, searchable_text

app = FastAPI(title="drivefind")

STATIC_DIR = Path(__file__).parent / "static"


@lru_cache
def get_ai_provider() -> AIRecordProvider:
    if config.ANTHROPIC_API_KEY:
        return AnthropicRecordProvider()
    return FakeAIRecordProvider()


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    if config.VOYAGE_API_KEY:
        return VoyageEmbeddingProvider()
    return FakeEmbeddingProvider()


def _record_to_drive_file(record: store.FileRecord) -> DriveFile:
    return DriveFile(
        id=record.id,
        name=record.name,
        mime_type=record.mime_type,
        size=record.size,
        modified_time=record.modified_time,
        web_view_link=record.web_view_link,
        checksum=None,
    )


@app.get("/", response_class=HTMLResponse)
def index_page() -> str:
    return (STATIC_DIR / "index.html").read_text()


class IndexResponse(BaseModel):
    scanned: int
    indexed: int
    skipped_unchanged: int
    failed: int
    using_fake_ai: bool
    using_fake_embeddings: bool


@app.post("/api/index", response_model=IndexResponse)
def trigger_index() -> IndexResponse:
    drive = DriveClient()
    summary = run_index(store.connect(), drive, get_ai_provider(), get_embedding_provider())
    return IndexResponse(
        scanned=summary.scanned,
        indexed=summary.indexed,
        skipped_unchanged=summary.skipped_unchanged,
        failed=summary.failed,
        using_fake_ai=isinstance(get_ai_provider(), FakeAIRecordProvider),
        using_fake_embeddings=isinstance(get_embedding_provider(), FakeEmbeddingProvider),
    )


class SearchResult(BaseModel):
    id: str
    name: str
    mime_type: str
    description: str | None
    tags: list[str]
    subtitle: str | None
    web_view_link: str | None
    score: float


@app.get("/api/search", response_model=list[SearchResult])
def search(q: str, top_k: int = 10) -> list[SearchResult]:
    conn = store.connect()
    query_embedding = get_embedding_provider().embed_one(q)
    results = store.search(conn, query_embedding, top_k=top_k)
    return [
        SearchResult(
            id=r.id,
            name=r.name,
            mime_type=r.mime_type,
            description=r.description,
            tags=r.tags,
            subtitle=r.subtitle,
            web_view_link=r.web_view_link,
            score=score,
        )
        for r, score in results
    ]


class RecordUpdate(BaseModel):
    description: str | None = None
    tags: list[str] | None = None
    subtitle: str | None = None


@app.patch("/api/files/{file_id}", response_model=SearchResult)
def update_record(file_id: str, update: RecordUpdate) -> SearchResult:
    conn = store.connect()
    existing = store.get_file(conn, file_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="File not found in the index.")

    description = update.description if update.description is not None else existing.description or ""
    tags = update.tags if update.tags is not None else existing.tags
    subtitle = update.subtitle if update.subtitle is not None else existing.subtitle or ""

    new_embedding = get_embedding_provider().embed_one(
        searchable_text(existing.name, subtitle, description, tags)
    )
    store.update_record(conn, file_id, description=description, tags=tags, subtitle=subtitle, embedding=new_embedding)

    updated = store.get_file(conn, file_id)
    return SearchResult(
        id=updated.id,
        name=updated.name,
        mime_type=updated.mime_type,
        description=updated.description,
        tags=updated.tags,
        subtitle=updated.subtitle,
        web_view_link=updated.web_view_link,
        score=1.0,
    )


@app.get("/api/download/{file_id}")
def download(file_id: str) -> StreamingResponse:
    conn = store.connect()
    record = store.get_file(conn, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="File not found in the index.")

    drive = DriveClient()
    content, effective_mime = drive.fetch_bytes(_record_to_drive_file(record))
    return StreamingResponse(
        io.BytesIO(content),
        media_type=effective_mime,
        headers={"Content-Disposition": f'attachment; filename="{record.name}"'},
    )

"""Generates the searchable record (description, tags, subtitle) for a file.

Abstracted behind AIRecordProvider so the real Anthropic-backed provider can
be swapped for FakeAIRecordProvider in tests/offline runs, without network
or an API key.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from . import config

SYSTEM_PROMPT = (
    "You catalog files for a semantic search index. Given a filename, its type, "
    "and (if available) its extracted text content, produce a short record that "
    "will be embedded and searched against later. Be concrete and specific — "
    "mention real entities, topics, and keywords from the content rather than "
    "generic filler. If no content was extracted, do your best from the filename "
    "and type alone, and keep the description short and hedged."
)


@dataclass
class AIRecord:
    description: str
    tags: list[str]
    subtitle: str


class AIRecordProvider(ABC):
    @abstractmethod
    def generate(self, filename: str, mime_type: str, text: str | None) -> AIRecord: ...


class AnthropicRecordProvider(AIRecordProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        import anthropic  # local import: optional dependency until this provider is used

        api_key = api_key or config.ANTHROPIC_API_KEY
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model or config.ANTHROPIC_MODEL

    def generate(self, filename: str, mime_type: str, text: str | None) -> AIRecord:
        content_block = f"\n\nExtracted content (may be truncated):\n{text}" if text else "\n\nNo text could be extracted from this file."
        user_message = f"Filename: {filename}\nMIME type: {mime_type}{content_block}"

        response = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            tools=[
                {
                    "name": "emit_record",
                    "description": "Emit the catalog record for this file.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "One to three sentences describing the file's actual content.",
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "3-8 short lowercase keyword tags.",
                            },
                            "subtitle": {
                                "type": "string",
                                "description": "A single short tagline, under 10 words.",
                            },
                        },
                        "required": ["description", "tags", "subtitle"],
                    },
                }
            ],
            tool_choice={"type": "tool", "name": "emit_record"},
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "emit_record":
                data = block.input
                return AIRecord(
                    description=data["description"],
                    tags=[t.lower() for t in data["tags"]],
                    subtitle=data["subtitle"],
                )

        raise RuntimeError("Anthropic response did not include the expected tool call.")


class FakeAIRecordProvider(AIRecordProvider):
    """Deterministic, offline, no-API-key stand-in for tests and dev runs."""

    def generate(self, filename: str, mime_type: str, text: str | None) -> AIRecord:
        words = re.findall(r"[a-zA-Z0-9]+", filename.lower())
        tags = sorted(set(w for w in words if len(w) > 2))[:8] or ["untitled"]
        snippet = f" Starts with: {text[:80]!r}." if text else ""
        return AIRecord(
            description=f"A {mime_type} file named '{filename}'.{snippet}",
            tags=tags,
            subtitle=filename,
        )

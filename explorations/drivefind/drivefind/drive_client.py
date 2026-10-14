"""Thin wrapper around the Google Drive API: OAuth, listing, and downloads.

Google native formats (Docs, Sheets, Slides) have no raw bytes to download —
they must be *exported* as a concrete format (we use plain text for Docs,
CSV for Sheets) to get extractable content or a downloadable file at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

from . import config

LIST_FIELDS = "nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink, md5Checksum)"

GOOGLE_NATIVE_EXPORTS = {
    "application/vnd.google-apps.document": ("text/plain", ".txt"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation": ("text/plain", ".txt"),
}


@dataclass
class DriveFile:
    id: str
    name: str
    mime_type: str
    size: int | None
    modified_time: str | None
    web_view_link: str | None
    checksum: str | None

    @property
    def is_google_native(self) -> bool:
        return self.mime_type.startswith("application/vnd.google-apps")

    @property
    def change_token(self) -> str:
        """What we compare against to decide whether a file needs re-indexing."""
        return self.checksum or self.modified_time or ""


def _load_credentials() -> Credentials:
    config.ensure_data_dir()
    creds: Credentials | None = None
    if config.TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(config.TOKEN_FILE), config.DRIVE_SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if not config.CLIENT_SECRETS_FILE.exists():
            raise RuntimeError(
                f"No Google OAuth client secrets found at {config.CLIENT_SECRETS_FILE}. "
                "Create an OAuth client (Desktop app type) in Google Cloud Console, enable the "
                "Drive API, and download its JSON there. See README.md for the full steps."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(config.CLIENT_SECRETS_FILE), config.DRIVE_SCOPES)
        creds = flow.run_local_server(port=0)
        config.TOKEN_FILE.write_text(creds.to_json())

    return creds


class DriveClient:
    def __init__(self) -> None:
        self._service = build("drive", "v3", credentials=_load_credentials())

    def list_files(self, page_size: int = 100) -> Iterator[DriveFile]:
        page_token = None
        while True:
            resp = (
                self._service.files()
                .list(
                    pageSize=page_size,
                    fields=LIST_FIELDS,
                    q="trashed = false",
                    pageToken=page_token,
                )
                .execute()
            )
            for f in resp.get("files", []):
                yield DriveFile(
                    id=f["id"],
                    name=f["name"],
                    mime_type=f["mimeType"],
                    size=int(f["size"]) if "size" in f else None,
                    modified_time=f.get("modifiedTime"),
                    web_view_link=f.get("webViewLink"),
                    checksum=f.get("md5Checksum"),
                )
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    def fetch_bytes(self, file: DriveFile) -> tuple[bytes, str]:
        """Returns (content, effective_mime_type). Exports Google-native files."""
        if file.is_google_native:
            export_mime, _ext = GOOGLE_NATIVE_EXPORTS.get(file.mime_type, ("text/plain", ".txt"))
            request = self._service.files().export_media(fileId=file.id, mimeType=export_mime)
            effective_mime = export_mime
        else:
            request = self._service.files().get_media(fileId=file.id)
            effective_mime = file.mime_type

        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _status, done = downloader.next_chunk()
        return buf.getvalue(), effective_mime

# drivefind

AI-powered semantic search over your Google Drive. For every file, drivefind
generates a description, tags, and a short subtitle (via Claude), embeds
them (via Voyage AI) for real semantic similarity search, and lets you
search and download files from a small local web UI.

This was prototyped in a sandboxed environment that can't reach Google's
OAuth endpoints or Voyage AI's API — those steps are untested live. Run it
on your own machine to actually use it against your Drive.

## How it works

1. **Index**: lists your Drive files, downloads/extracts text where
   possible (plain text, PDF, and Google Docs/Sheets/Slides via export),
   and for each new or changed file asks Claude to generate a
   `description` + `tags` + `subtitle`. Those get embedded with Voyage AI
   and stored, along with the file's metadata, in a local SQLite database
   (`~/.drivefind/drivefind.sqlite3`).
2. **Search**: your query is embedded the same way and compared against
   every stored file's embedding by cosine similarity; the closest matches
   come back ranked.
3. **Edit**: any record's description/tags/subtitle can be edited by hand
   in the UI — edited records are marked so a later re-index won't
   overwrite your edits (only an actual change to the file will).
4. **Download**: pulls the real file bytes from Drive and streams them to
   your browser.

Records live only in the local SQLite file, not written back to Drive.

## Setup

### 1. Google OAuth client (required for Drive access)

1. In [Google Cloud Console](https://console.cloud.google.com/), create a
   project (or use an existing one) and enable the **Google Drive API**.
2. Under **APIs & Services → Credentials**, create an **OAuth client ID**
   of type **Desktop app**.
3. Download its JSON and save it as `~/.drivefind/client_secret.json`
   (or point `DRIVEFIND_CLIENT_SECRETS` at wherever you put it).
4. The first time you click "Re-index Drive" in the UI, a browser window
   will open for you to sign in and grant read-only Drive access. The
   resulting token is cached in `~/.drivefind/token.json` so you won't be
   asked again until it expires.

### 2. API keys

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # for generating descriptions/tags/subtitles
export VOYAGE_API_KEY=pa-...          # for embeddings (voyageai.com)
```

Without these, drivefind still runs — it falls back to a placeholder
AI-record generator and a placeholder embedding function so you can see
the pipeline work, but results won't be real.

### 3. Install and run

```bash
pip install -e .
drivefind
```

Then open http://127.0.0.1:8420, click **Re-index Drive** (first run will
be slow — one Claude + one Voyage call per file), and search.

## Config

All via environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `DRIVEFIND_DATA_DIR` | `~/.drivefind` | Where the DB, OAuth client secret, and token are stored |
| `DRIVEFIND_CLIENT_SECRETS` | `<data dir>/client_secret.json` | Google OAuth client JSON |
| `DRIVEFIND_TOKEN_FILE` | `<data dir>/token.json` | Cached OAuth token |
| `DRIVEFIND_DB` | `<data dir>/drivefind.sqlite3` | SQLite database path |
| `ANTHROPIC_API_KEY` | — | Enables real AI-generated records |
| `VOYAGE_API_KEY` | — | Enables real semantic embeddings |
| `DRIVEFIND_ANTHROPIC_MODEL` | `claude-sonnet-5-5` | Model used to generate records |
| `DRIVEFIND_VOYAGE_MODEL` | `voyage-3.5` | Embedding model |
| `DRIVEFIND_MAX_EXTRACT_CHARS` | `20000` | Truncation limit for extracted text sent to the model |

## Known gaps (prototype scope)

- Only plain text, PDF, and Google-native (Docs/Sheets/Slides) files get
  real content extraction; everything else gets a record generated from
  just the filename and type.
- "Subtitle" here means a short AI-written tagline, not actual audio/video
  captions — real transcription of audio/video files is a separate,
  bigger feature if that's what's wanted.
- Indexing runs synchronously in the request — on a large Drive this will
  be slow and the request will just hang until it's done. Fine for
  exploring the idea, not for a real Drive of any size.
- No incremental/partial-failure retry UI — failed files are silently
  skipped and counted in the summary.

"""Notes MCP server.

A from-scratch Model Context Protocol server that gives an MCP client
(e.g. Claude Desktop) a small but fully working personal-notes store.

Stack:
    - Python 3.10+
    - official `mcp` package (FastMCP high-level API)
    - transport: stdio

Storage is a real JSON file on disk (NOT a stub), so notes persist across
restarts of the server and of Claude Desktop. Override the location with the
`NOTES_DB_PATH` environment variable; otherwise it defaults to
`~/.mcp_notes/notes.json`.

Exposed capabilities
--------------------
Tools:
    add_note(content, title?, tags?)   -> create a note   (required + optional args)
    search_notes(query, tag?, limit?)  -> full-text search (required + optional args)
    delete_note(note_id)               -> delete a note   (required arg)

Resources:
    notes://all        -> every note, formatted as text
    notes://stats      -> aggregate statistics about the store
    note://{note_id}   -> a single note by id (resource template)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# --------------------------------------------------------------------------- #
# Storage layer (real, file-backed persistence)
# --------------------------------------------------------------------------- #

DB_PATH = Path(
    os.environ.get("NOTES_DB_PATH", Path.home() / ".mcp_notes" / "notes.json")
).expanduser()


def _now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> dict[str, Any]:
    """Load the notes database from disk, creating an empty one if needed."""
    if not DB_PATH.exists():
        return {"next_id": 1, "notes": []}
    try:
        with DB_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        # Corrupt or unreadable file -> start fresh rather than crash the server.
        return {"next_id": 1, "notes": []}
    data.setdefault("next_id", 1)
    data.setdefault("notes", [])
    return data


def _save(data: dict[str, Any]) -> None:
    """Persist the notes database to disk atomically."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp.replace(DB_PATH)  # atomic on the same filesystem


def _format_note(note: dict[str, Any]) -> str:
    """Render a single note as a human-readable block."""
    tags = ", ".join(note.get("tags") or []) or "—"
    title = note.get("title") or "(untitled)"
    return (
        f"#{note['id']}  {title}\n"
        f"  tags:    {tags}\n"
        f"  created: {note['created_at']}\n"
        f"  updated: {note['updated_at']}\n"
        f"  {note['content']}"
    )


# --------------------------------------------------------------------------- #
# MCP server
# --------------------------------------------------------------------------- #

mcp = FastMCP("notes")


# ----------------------------------- tools --------------------------------- #

@mcp.tool()
def add_note(
    content: str,
    title: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Create a new note.

    Args:
        content: The body of the note. REQUIRED.
        title:   Optional short title. If omitted, the note is "(untitled)".
        tags:    Optional list of tags for later filtering, e.g. ["work", "idea"].

    Returns:
        A confirmation message including the new note's id.
    """
    if not content or not content.strip():
        return "Error: 'content' must not be empty."

    data = _load()
    note = {
        "id": data["next_id"],
        "title": (title or "").strip() or None,
        "content": content.strip(),
        "tags": [t.strip() for t in (tags or []) if t.strip()],
        "created_at": _now(),
        "updated_at": _now(),
    }
    data["notes"].append(note)
    data["next_id"] += 1
    _save(data)
    return f"Note #{note['id']} saved (title: {note['title'] or '(untitled)'})."


@mcp.tool()
def search_notes(query: str, tag: str | None = None, limit: int = 10) -> str:
    """Search notes by text and optionally filter by tag.

    Args:
        query: Case-insensitive substring to match in title or content. REQUIRED.
               Pass "*" to match every note.
        tag:   Optional tag to filter by (exact, case-insensitive match).
        limit: Optional maximum number of results to return (default 10).

    Returns:
        Formatted matching notes, or a "no matches" message.
    """
    data = _load()
    q = query.strip().lower()
    tag_l = tag.strip().lower() if tag else None

    matches: list[dict[str, Any]] = []
    for note in data["notes"]:
        haystack = f"{note.get('title') or ''} {note['content']}".lower()
        text_ok = q == "*" or q in haystack
        tag_ok = tag_l is None or tag_l in [t.lower() for t in note.get("tags", [])]
        if text_ok and tag_ok:
            matches.append(note)

    # Newest first.
    matches.sort(key=lambda n: n["created_at"], reverse=True)
    matches = matches[: max(1, limit)]

    if not matches:
        filt = f" with tag '{tag}'" if tag else ""
        return f"No notes found for query '{query}'{filt}."

    header = f"Found {len(matches)} note(s):\n\n"
    return header + "\n\n".join(_format_note(n) for n in matches)


@mcp.tool()
def delete_note(note_id: int) -> str:
    """Delete a note by its id.

    Args:
        note_id: The id of the note to delete. REQUIRED.

    Returns:
        A confirmation or a "not found" message.
    """
    data = _load()
    before = len(data["notes"])
    data["notes"] = [n for n in data["notes"] if n["id"] != note_id]
    if len(data["notes"]) == before:
        return f"No note with id #{note_id} was found."
    _save(data)
    return f"Note #{note_id} deleted."


# --------------------------------- resources ------------------------------- #

@mcp.resource("notes://all")
def all_notes() -> str:
    """All notes in the store, formatted as text (newest first)."""
    data = _load()
    notes = sorted(data["notes"], key=lambda n: n["created_at"], reverse=True)
    if not notes:
        return "The notes store is empty. Use the add_note tool to create one."
    return "\n\n".join(_format_note(n) for n in notes)


@mcp.resource("notes://stats")
def stats() -> str:
    """Aggregate statistics about the notes store (JSON)."""
    data = _load()
    notes = data["notes"]
    tag_counts: dict[str, int] = {}
    for note in notes:
        for tag in note.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    payload = {
        "total_notes": len(notes),
        "unique_tags": len(tag_counts),
        "tag_counts": dict(sorted(tag_counts.items(), key=lambda kv: -kv[1])),
        "last_updated": max((n["updated_at"] for n in notes), default=None),
        "db_path": str(DB_PATH),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.resource("note://{note_id}")
def single_note(note_id: str) -> str:
    """A single note addressed by id, e.g. note://3 (resource template)."""
    data = _load()
    try:
        wanted = int(note_id)
    except ValueError:
        return f"'{note_id}' is not a valid note id."
    for note in data["notes"]:
        if note["id"] == wanted:
            return _format_note(note)
    return f"No note with id #{note_id} was found."


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # Run over stdio so Claude Desktop can launch and talk to the server.
    mcp.run(transport="stdio")

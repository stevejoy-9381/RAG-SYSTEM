"""
src/document_store.py — Per-User Document Registry (Phase 3 Update)
────────────────────────────────────────────────────────────────────
WHAT CHANGED FROM PHASE 1/2:

  Phase 1/2: ONE shared document registry at vectorstore/documents.json
             → All users shared the same document library (wrong!)

  Phase 3: ONE registry PER USER at vectorstore/{user_id}/documents.json
             → Alice's uploads are invisible to Bob and vice versa
             → Each user has a fully isolated document library

  The API is identical — all functions now take a user_id parameter.
  api.py passes the user_id from the JWT token to every document operation.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional


def _get_registry_path(user_id: str) -> str:
    """Return the path to this user's document registry file."""
    return f"vectorstore/{user_id}/documents.json"


def _load_registry(user_id: str) -> dict:
    path = _get_registry_path(user_id)
    if not os.path.exists(path):
        return {"documents": []}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"documents": []}


def _save_registry(user_id: str, registry: dict) -> None:
    path = _get_registry_path(user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(registry, f, indent=2)


def register_document(
    user_id: str,
    filename: str,
    pages: int,
    chunks: int,
    size_kb: float = 0.0,
) -> None:
    """Add or update a document entry in this user's registry."""
    registry = _load_registry(user_id)
    entry = {
        "filename":    filename,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "pages":       pages,
        "chunks":      chunks,
        "size_kb":     round(size_kb, 1),
    }
    existing = [d["filename"] for d in registry["documents"]]
    if filename in existing:
        idx = existing.index(filename)
        registry["documents"][idx] = entry
        print(f"[DOCSTORE] User '{user_id[:8]}': updated '{filename}'")
    else:
        registry["documents"].append(entry)
        print(f"[DOCSTORE] User '{user_id[:8]}': registered '{filename}'")
    _save_registry(user_id, registry)


def get_all_documents(user_id: str) -> list[dict]:
    """Return all documents for this user."""
    return _load_registry(user_id)["documents"]


def is_duplicate(user_id: str, filename: str) -> bool:
    """Check if this user already has a document with this filename."""
    return filename in [d["filename"] for d in get_all_documents(user_id)]


def remove_document(user_id: str, filename: str) -> bool:
    """Remove a document from this user's registry."""
    registry = _load_registry(user_id)
    original = len(registry["documents"])
    registry["documents"] = [
        d for d in registry["documents"] if d["filename"] != filename
    ]
    removed = len(registry["documents"]) < original
    if removed:
        _save_registry(user_id, registry)
        print(f"[DOCSTORE] User '{user_id[:8]}': removed '{filename}'")
    return removed


def get_document_stats(user_id: str) -> dict:
    """Return summary statistics for this user's document library."""
    docs = get_all_documents(user_id)
    return {
        "total_documents": len(docs),
        "total_pages":     sum(d.get("pages", 0) for d in docs),
        "total_chunks":    sum(d.get("chunks", 0) for d in docs),
        "documents":       docs,
    }

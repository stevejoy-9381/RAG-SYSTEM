"""
src/ingest.py — Per-User Ingestion Pipeline (Phase 3 Update)
──────────────────────────────────────────────────────────────
WHAT CHANGED FROM PHASE 1/2:

  Phase 1/2: FAISS index saved at vectorstore/faiss_index/
             → all users shared one index (wrong!)

  Phase 3:   FAISS index saved at vectorstore/{user_id}/faiss_index/
             → each user has a completely isolated vector index

  The run_ingestion() function now requires a user_id parameter.
  Everything else (chunking, embedding, append-mode) is identical.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from langchain_community.document_loaders import PyMuPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from src.document_store import register_document


CHUNK_SIZE       = int(os.getenv("CHUNK_SIZE", 800))
CHUNK_OVERLAP    = int(os.getenv("CHUNK_OVERLAP", 100))
EMBEDDING_MODEL  = "sentence-transformers/all-MiniLM-L6-v2"


def get_user_index_path(user_id: str) -> str:
    """Return the FAISS index path for a specific user."""
    return f"vectorstore/{user_id}/faiss_index"


def load_document(file_path: str) -> list:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Only .pdf supported. Got: '{path.suffix}'")
    loader = PyMuPDFLoader(str(path))
    docs = loader.load()
    print(f"[INGEST] Loaded {len(docs)} pages from '{path.name}'")
    return docs


def enrich_metadata(documents: list, original_filename: str) -> list:
    """Attach clean metadata to each page (filename, time, total pages)."""
    upload_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    total_pages = len(documents)
    for doc in documents:
        doc.metadata["source"]      = original_filename
        doc.metadata["upload_time"] = upload_time
        doc.metadata["total_pages"] = total_pages
    return documents


def chunk_documents(documents: list) -> list:
    """Split pages into well-sized, overlapping chunks."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n\n", "\n\n", "\n", ". ", "; ", ": ", " ", ""],
        length_function=len,
    )
    chunks = splitter.split_documents(documents)

    # Add chunk index metadata for richer citations
    source_counts: dict = {}
    for chunk in chunks:
        src = chunk.metadata.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1
        chunk.metadata["chunk_index"] = source_counts[src]

    avg = sum(len(c.page_content) for c in chunks) // max(len(chunks), 1)
    print(f"[INGEST] {len(chunks)} chunks created (avg {avg} chars)")
    return chunks


def get_embedding_model() -> HuggingFaceEmbeddings:
    """Load and return the embedding model (downloads once, cached locally)."""
    print(f"[INGEST] Loading embedding model...")
    model = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    print("[INGEST] Embedding model ready.")
    return model


def append_to_user_index(
    user_id: str,
    chunks: list,
    embedding_model: HuggingFaceEmbeddings,
) -> int:
    """
    Append new document chunks to this user's FAISS index.

    Identical logic to Phase 1 append_to_index() but uses the
    per-user path from get_user_index_path().
    """
    index_path = get_user_index_path(user_id)
    os.makedirs(index_path, exist_ok=True)

    print(f"[INGEST] Embedding {len(chunks)} chunks for user '{user_id[:8]}'...")
    new_vs = FAISS.from_documents(chunks, embedding_model)

    index_file = os.path.join(index_path, "index.faiss")
    if os.path.exists(index_file):
        print("[INGEST] Existing index found — merging...")
        existing_vs = FAISS.load_local(
            index_path, embedding_model,
            allow_dangerous_deserialization=True,
        )
        existing_vs.merge_from(new_vs)
        existing_vs.save_local(index_path)
        print("[INGEST] Merge complete.")
    else:
        new_vs.save_local(index_path)
        print("[INGEST] Fresh index created.")

    return len(chunks)


def run_ingestion(
    file_path: str,
    user_id: str,
    original_filename: str = None,
) -> dict:
    """
    Master ingestion function — now requires user_id for isolation.

    PIPELINE:
      file → load → enrich metadata → chunk → embed
            → append to user's FAISS index → register in user's document store
    """
    display_name = original_filename or Path(file_path).name
    file_size_kb = Path(file_path).stat().st_size / 1024

    print(f"\n[INGEST] user='{user_id[:8]}' file='{display_name}'")

    documents      = load_document(file_path)
    documents      = enrich_metadata(documents, display_name)
    chunks         = chunk_documents(documents)
    embedding_model = get_embedding_model()
    total_chunks   = append_to_user_index(user_id, chunks, embedding_model)

    register_document(
        user_id=user_id,
        filename=display_name,
        pages=len(documents),
        chunks=total_chunks,
        size_kb=file_size_kb,
    )

    print(f"[INGEST] ✓ Done: {len(documents)} pages, {total_chunks} chunks\n")
    return {
        "status": "success",
        "file":   display_name,
        "pages":  len(documents),
        "chunks": total_chunks,
    }

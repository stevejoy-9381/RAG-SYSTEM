"""
src/retriever.py — Per-User Hybrid Retrieval (Phase 3 Update)
──────────────────────────────────────────────────────────────
WHAT CHANGED FROM PHASE 2:

  Phase 2: ONE global retriever cache (_retriever_cache)
           ONE global QA chain (_qa_chain in api.py)
           → Alice's retriever searched Bob's documents too (wrong!)

  Phase 3: PER-USER retriever cache (_retriever_cache: dict[user_id, retriever])
           → Alice's retriever only searches Alice's FAISS index
           → Bob's retriever only searches Bob's FAISS index
           → Completely isolated, as required

  The embedding model is still shared (same model for all users — correct).
  Only the FAISS index and BM25 index are per-user.
"""

import os
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever
from langchain.chains import RetrievalQA

from src.llm import get_llm, get_prompt_template
from src.ingest import get_user_index_path


EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RETRIEVAL_K     = int(os.getenv("RETRIEVAL_K", 4))
BM25_WEIGHT     = float(os.getenv("BM25_WEIGHT", 0.4))
FAISS_WEIGHT    = float(os.getenv("FAISS_WEIGHT", 0.6))


# ─── Cache ────────────────────────────────────────────────────────────────────
# Embedding model: shared across all users (one model, identical weights)
# Retriever: per-user dict — each user's key stores their EnsembleRetriever
_embedding_model_cache: HuggingFaceEmbeddings | None = None
_retriever_cache: dict[str, EnsembleRetriever] = {}   # {user_id: retriever}


def invalidate_user_cache(user_id: str) -> None:
    """
    Remove this user's cached retriever.
    Called after they upload a new document or delete one.
    The next request rebuilds the retriever from the updated index.
    """
    if user_id in _retriever_cache:
        del _retriever_cache[user_id]
        print(f"[RETRIEVER] Cache invalidated for user '{user_id[:8]}'")


def _get_embedding_model() -> HuggingFaceEmbeddings:
    """Load embedding model once, reuse for all users."""
    global _embedding_model_cache
    if _embedding_model_cache is None:
        print(f"[RETRIEVER] Loading embedding model...")
        _embedding_model_cache = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        print("[RETRIEVER] Embedding model loaded and cached.")
    return _embedding_model_cache


def _check_user_index(user_id: str) -> None:
    """Raise a clear error if this user has no FAISS index yet."""
    index_path = get_user_index_path(user_id)
    if not os.path.exists(os.path.join(index_path, "index.faiss")):
        raise FileNotFoundError(
            "You haven't uploaded any documents yet. "
            "Upload a PDF first to start asking questions."
        )


def get_hybrid_retriever(user_id: str) -> EnsembleRetriever:
    """
    Return the hybrid BM25 + FAISS retriever for a specific user.

    CACHE HIT:   return cached retriever for this user instantly
    CACHE MISS:  build retriever from this user's FAISS index, cache it

    ISOLATION GUARANTEE:
      get_user_index_path(user_id) returns a unique path per user.
      FAISS.load_local() reads only THAT user's index.
      BM25 is built from docs in THAT user's FAISS docstore.
      → User A's retriever cannot access User B's documents.
    """
    _check_user_index(user_id)

    if user_id in _retriever_cache:
        return _retriever_cache[user_id]

    print(f"[RETRIEVER] Building retriever for user '{user_id[:8]}'...")
    embedding_model = _get_embedding_model()
    index_path = get_user_index_path(user_id)

    vectorstore = FAISS.load_local(
        index_path, embedding_model,
        allow_dangerous_deserialization=True,
    )

    all_docs = list(vectorstore.docstore._dict.values())
    if not all_docs:
        raise ValueError("Your document index is empty. Re-upload your documents.")

    bm25 = BM25Retriever.from_documents(all_docs)
    bm25.k = RETRIEVAL_K

    faiss_ret = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": RETRIEVAL_K},
    )

    ensemble = EnsembleRetriever(
        retrievers=[bm25, faiss_ret],
        weights=[BM25_WEIGHT, FAISS_WEIGHT],
    )

    _retriever_cache[user_id] = ensemble
    print(f"[RETRIEVER] Retriever cached for user '{user_id[:8]}'.")
    return ensemble


def build_qa_chain(user_id: str) -> RetrievalQA:
    """Build the full QA chain for this user's index (for /ask endpoint)."""
    retriever = get_hybrid_retriever(user_id)
    qa_chain = RetrievalQA.from_chain_type(
        llm=get_llm(),
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": get_prompt_template()},
    )
    return qa_chain


def format_sources(docs: list) -> list[dict]:
    """Format retrieved documents into clean source citation dicts."""
    sources = []
    seen = set()
    for doc in docs:
        key = doc.page_content[:100]
        if key in seen:
            continue
        seen.add(key)
        meta = doc.metadata
        sources.append({
            "file":        meta.get("source", "unknown"),
            "page":        meta.get("page", 0) + 1,
            "total_pages": meta.get("total_pages", "?"),
            "chunk_index": meta.get("chunk_index", "?"),
            "upload_time": meta.get("upload_time", ""),
            "preview": (
                doc.page_content[:300] + "..."
                if len(doc.page_content) > 300
                else doc.page_content
            ),
        })
    return sources

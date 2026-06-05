"""
Semantic caching layer using ChromaDB + Gemini embeddings.

Flow:
  read_cache(question)  → cached response str | None
  write_cache(question, response)  → None  (fire-and-forget safe)

A hit is defined as cosine distance < CACHE_DISTANCE_THRESHOLD, which
corresponds to semantically similar questions including moderate rephrasing.
"""

from __future__ import annotations

import logging
import os
import ssl
import uuid

import chromadb
from langchain_google_genai import GoogleGenerativeAIEmbeddings

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
CACHE_COLLECTION_NAME = "semantic_cache"
CACHE_DISTANCE_THRESHOLD = 0.40   # L2 distance; <0.40 tolerates moderate rephrasing
EMBEDDING_MODEL = "models/gemini-embedding-001"


# ── Shared singletons (initialised once per process) ─────────────────────────
_chroma_client: chromadb.PersistentClient | None = None
_cache_collection: chromadb.Collection | None = None
_embedder: GoogleGenerativeAIEmbeddings | None = None


def _ssl_client_args() -> dict:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return {"verify": ctx}


def _get_embedder() -> GoogleGenerativeAIEmbeddings:
    global _embedder
    if _embedder is None:
        _embedder = GoogleGenerativeAIEmbeddings(
            model=EMBEDDING_MODEL,
            client_args=_ssl_client_args(),
        )
    return _embedder


def _get_collection() -> chromadb.Collection:
    global _chroma_client, _cache_collection
    if _cache_collection is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
        _cache_collection = _chroma_client.get_or_create_collection(
            name=CACHE_COLLECTION_NAME,
            metadata={"hnsw:space": "l2"},
        )
    return _cache_collection


def _embed(text: str) -> list[float]:
    return _get_embedder().embed_query(text)


# ── Public API ────────────────────────────────────────────────────────────────

def read_cache(question: str) -> str | None:
    """
    Return a cached assistant response if a semantically near-identical
    question has been seen before, otherwise return None.
    """
    try:
        collection = _get_collection()
        if collection.count() == 0:
            return None

        vector = _embed(question)
        results = collection.query(
            query_embeddings=[vector],
            n_results=1,
            include=["distances", "metadatas"],
        )

        distances: list[float] = (results.get("distances") or [[]])[0]
        metadatas: list[dict] = (results.get("metadatas") or [[]])[0]

        if not distances:
            print("🔍 Cache check: collection has entries but query returned no distances.")
            return None

        best_distance = distances[0]

        # Always print the closest distance — helps calibrate the threshold
        print(f"🔍 Cache check: Closest match distance is {best_distance:.4f} "
              f"(threshold={CACHE_DISTANCE_THRESHOLD})")

        if best_distance < CACHE_DISTANCE_THRESHOLD:
            cached_response: str = metadatas[0].get("response", "")
            logger.info(
                "Semantic cache HIT (distance=%.4f) for: %.80s",
                best_distance,
                question,
            )
            return cached_response

        logger.debug(
            "Semantic cache MISS (distance=%.4f) for: %.80s",
            best_distance,
            question,
        )
        return None

    except Exception as exc:
        # Never let a cache failure break the main request path
        logger.error("semantic_cache.read_cache error: %s", exc, exc_info=True)
        return None


def write_cache(question: str, response: str) -> None:
    """
    Persist a question→response pair.  Safe to call from asyncio.to_thread.
    """
    try:
        collection = _get_collection()
        vector = _embed(question)
        collection.add(
            ids=[str(uuid.uuid4())],
            embeddings=[vector],
            documents=[question],
            metadatas=[{"response": response}],
        )
        logger.info("Semantic cache WRITE for: %.80s", question)
    except Exception as exc:
        logger.error("semantic_cache.write_cache error: %s", exc, exc_info=True)

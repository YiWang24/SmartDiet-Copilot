"""Railtracks configuration for LLM and vector store initialization."""

from __future__ import annotations

__all__ = [
    "get_llm",
    "get_vector_store",
    "is_railtracks_enabled",
    "rt",
    "RAILTRACKS_AVAILABLE",
]

from functools import lru_cache
from pathlib import Path

import httpx

from app.core.config import Settings, get_settings

try:
    import railtracks as rt
    from railtracks.vector_stores.chroma import ChromaVectorStore
    RAILTRACKS_AVAILABLE = True
except Exception:  # pragma: no cover - environment dependent
    RAILTRACKS_AVAILABLE = False
    rt = None  # type: ignore
    ChromaVectorStore = None  # type: ignore

_VECTOR_BACKEND_SIGNATURE: tuple[str, str | None] | None = None
_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _resolve_vector_store_path(settings: Settings) -> str | None:
    """Resolve Chroma backend path according to configured runtime mode."""

    if settings.vector_store_mode == "memory":
        return None

    persist_path = Path(settings.chroma_persist_dir).expanduser()
    persist_path.mkdir(parents=True, exist_ok=True)
    return str(persist_path)


def _resolve_api_key(settings: Settings) -> str:
    """Resolve Gemini API key."""

    return (settings.gemini_api_key or "").strip()


def _normalize_llm_model_name(name: str) -> str:
    model_name = (name or "").strip()
    if model_name.startswith("models/"):
        model_name = model_name.split("/", 1)[1]
    if model_name.startswith("gemini/"):
        model_name = model_name.split("/", 1)[1]
    return model_name or "gemini-2.5-pro"


def _normalize_embedding_model_name(name: str) -> str:
    model_name = (name or "").strip()
    if model_name.startswith("gemini/"):
        model_name = model_name.split("/", 1)[1]
    if not model_name:
        model_name = "gemini-embedding-001"
    if model_name.startswith("models/"):
        return model_name
    return f"models/{model_name}"


def _single_embed_call(*, api_key: str, model: str, text: str) -> list[float]:
    """Call Gemini embedContent endpoint for one text."""

    url = f"{_GEMINI_API_BASE}/{model}:embedContent"
    payload = {
        "model": model,
        "content": {"parts": [{"text": text or " "}]},
        "taskType": "RETRIEVAL_DOCUMENT",
    }
    response = httpx.post(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=20.0,
    )
    response.raise_for_status()
    body = response.json()
    values = (body.get("embedding") or {}).get("values") or []
    if not values:
        raise RuntimeError("Gemini embedding response missing values")
    return [float(item) for item in values]


def _gemini_embed_texts(*, api_key: str, model: str, texts: list[str]) -> list[list[float]]:
    """Embed many texts via Gemini API."""

    if not texts:
        return []

    requests = [
        {
            "model": model,
            "content": {"parts": [{"text": text or " "}]},
            "taskType": "RETRIEVAL_DOCUMENT",
        }
        for text in texts
    ]
    url = f"{_GEMINI_API_BASE}/{model}:batchEmbedContents"

    try:
        response = httpx.post(
            url,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={"requests": requests},
            timeout=30.0,
        )
        response.raise_for_status()
        body = response.json()
        embeddings = body.get("embeddings") or []
        if len(embeddings) == len(texts):
            parsed: list[list[float]] = []
            for item in embeddings:
                values = item.get("values") or []
                if not values:
                    raise RuntimeError("Gemini batch embedding response missing values")
                parsed.append([float(v) for v in values])
            return parsed
    except Exception:
        # Fall back to single-item calls for maximal API compatibility.
        pass

    return [
        _single_embed_call(api_key=api_key, model=model, text=text)
        for text in texts
    ]


def _sync_chroma_backend_signature(mode: str, path: str | None) -> None:
    """Reset shared Chroma client if backend mode/path changed across runs."""

    global _VECTOR_BACKEND_SIGNATURE

    next_signature = (mode, path)
    if (
        _VECTOR_BACKEND_SIGNATURE is not None
        and _VECTOR_BACKEND_SIGNATURE != next_signature
        and ChromaVectorStore is not None
        and hasattr(ChromaVectorStore, "_chroma")
    ):
        delattr(ChromaVectorStore, "_chroma")
    _VECTOR_BACKEND_SIGNATURE = next_signature


@lru_cache(maxsize=1)
def get_llm():
    """Initialize and return cached Gemini LLM instance.

    Returns:
        GeminiLLM: Configured LLM instance for inference.

    Raises:
        RuntimeError: If Railtracks is not installed or API key is missing.
    """
    if not RAILTRACKS_AVAILABLE:
        raise RuntimeError(
            "Railtracks is not installed. Install with: pip install 'railtracks[chroma]>=0.1.0'"
        )

    settings: Settings = get_settings()

    api_key = _resolve_api_key(settings)
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is required")

    model_name = _normalize_llm_model_name(settings.gemini_model or settings.railtracks_model)
    return rt.llm.GeminiLLM(
        model_name=model_name,
        api_key=api_key,
        api_base=settings.railtracks_base_url or None,
    )


@lru_cache(maxsize=1)
def get_vector_store() -> ChromaVectorStore:
    """Initialize and return cached ChromaDB vector store instance.

    Creates a persistent ChromaDB collection for RAG operations.
    The collection is stored in the configured persist directory.

    Returns:
        ChromaVectorStore: Configured vector store for semantic search.

    Raises:
        RuntimeError: If Railtracks/ChromaDB is not installed.
    """
    if not RAILTRACKS_AVAILABLE:
        raise RuntimeError(
            "Railtracks is not installed. Install with: pip install 'railtracks[chroma]>=0.1.0'"
        )

    settings: Settings = get_settings()

    path = _resolve_vector_store_path(settings)
    _sync_chroma_backend_signature(settings.vector_store_mode, path)

    api_key = _resolve_api_key(settings)
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is required for vector embedding")
    embedding_model = _normalize_embedding_model_name(settings.gemini_embedding_model)

    def _embed(texts: list[str]) -> list[list[float]]:
        return _gemini_embed_texts(api_key=api_key, model=embedding_model, texts=texts)

    return ChromaVectorStore(
        collection_name=settings.chroma_collection_name,
        embedding_function=_embed,
        path=path,
    )


def is_railtracks_enabled() -> bool:
    """Check if Railtracks is properly configured and available.

    Returns:
        bool: True if Railtracks can be used, False otherwise.
    """
    settings: Settings = get_settings()
    return bool(
        RAILTRACKS_AVAILABLE
        and settings.railtracks_enabled
        and _resolve_api_key(settings)
    )

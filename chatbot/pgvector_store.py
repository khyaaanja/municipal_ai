"""pgvector-backed embedding storage.

This module is isolated so the rest of the app can import it without
hard-failing if pgvector isn't available.

Assumptions:
- PostgreSQL database with pgvector extension.
- Django model `SemanticEmbedding` lives in chatbot.models.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

from django.conf import settings


def is_pgvector_configured() -> bool:
    # Fast check: we import the model; if table/field aren't ready migrations will fail elsewhere.
    try:
        from chatbot.models import SemanticEmbedding  # noqa: F401
        return True
    except Exception:
        return False


def ensure_embedding(text: str) -> str:
    return (text or '').strip()


def embedding_model_name() -> str:
    return getattr(settings, 'GROQ_EMBEDDING_MODEL', 'text-embedding-3-small')


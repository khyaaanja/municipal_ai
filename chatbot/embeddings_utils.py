"""Embedding utilities (Groq) for Municipal AI.

Note: Vector persistence is handled via pgvector when available.
This module only deals with embedding generation.
"""

from __future__ import annotations

from typing import List

from .semantic_models import embed_with_groq


def get_embedding_1536(api_key: str, text: str, *, embedding_model: str = "text-embedding-3-small") -> List[float]:
    """Generate a 1536-dimensional embedding vector for `text`."""
    vec = embed_with_groq(api_key=api_key, text=text, model=embedding_model)
    # Defensive: some models can be different dims; hard-require 1536.
    if vec and len(vec) != 1536:
        raise ValueError(f"Expected 1536-dim embedding, got {len(vec)}")
    return vec


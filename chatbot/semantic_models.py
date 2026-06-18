"""Semantic search helpers for Municipal AI.

This module exists to keep vector/embedding logic isolated from the main
AI engine. It intentionally does not change any other application behavior.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

import requests


GROQ_EMBEDDING_URL = "https://api.groq.com/openai/v1/embeddings"


def _normalize(vec: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return list(vec)
    return [x / norm for x in vec]


def embed_with_groq(api_key: str, text: str, *, model: str, timeout_s: int = 30) -> List[float]:
    """Return 1536-dim embedding vector using Groq's OpenAI-compatible embeddings API."""
    if not text:
        return []

    resp = requests.post(
        GROQ_EMBEDDING_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": text,
        },
        timeout=timeout_s,
    )
    resp.raise_for_status()
    data = resp.json()
    # OpenAI schema: data: [{embedding: [...]}]
    return data["data"][0]["embedding"]


@dataclass(frozen=True)
class SemanticHit:
    source_type: str
    source_id: int
    title: str
    content: str
    score: float


def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    # Use normalized vectors for stability if caller already normalized.
    # Otherwise compute cosine directly.
    denom = math.sqrt(sum(x * x for x in vec_a)) * math.sqrt(sum(y * y for y in vec_b))
    if denom == 0:
        return 0.0
    return sum(a * b for a, b in zip(vec_a, vec_b)) / denom


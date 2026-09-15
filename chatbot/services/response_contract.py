"""Shared internal contract for AI responses.

The public chat APIs continue to expose their existing response fields.  This
contract keeps answer provenance and operational metadata consistent between
the synchronous engine and the AnswerEngine fallback path.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AIResponse:
    answer: str
    sources: list[str] = field(default_factory=list)
    source: str | None = None
    degraded: bool = False
    fallback: bool = False
    source_note: str | None = None
    latency_ms: float | None = None
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_answer_engine_dict(self) -> dict[str, Any]:
        """Return the legacy AnswerEngine shape plus shared metadata."""
        return {
            "answer": self.answer,
            "source": self.source or ("fallback" if self.fallback else "primary"),
            "degraded": self.degraded,
            "metadata": self.operation_metadata(),
        }

    def operation_metadata(self) -> dict[str, Any]:
        return {
            "sources": list(self.sources),
            "source_note": self.source_note,
            "fallback": self.fallback,
            "latency_ms": self.latency_ms,
            "request_id": self.request_id,
            **self.metadata,
        }


def answer_engine_response(
    answer: str,
    *,
    source: str,
    degraded: bool,
    sources: list[str] | None = None,
    latency_ms: float | None = None,
    request_id: str | None = None,
    source_note: str | None = None,
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build an AnswerEngine response without changing its public keys."""
    if sources is None and source in {"local_db", "fallback_model"}:
        sources = ["knowledge_base"]
    return AIResponse(
        answer=answer,
        source=source,
        degraded=degraded,
        fallback=degraded,
        sources=sources or [],
        latency_ms=latency_ms,
        request_id=request_id,
        source_note=source_note,
        metadata={"citations": citations or []},
    ).as_answer_engine_dict()


def request_id_from(request) -> str | None:
    """Read an optional request correlation id without requiring one."""
    if request is None:
        return None
    return request.headers.get("X-Request-ID") or request.META.get("HTTP_X_REQUEST_ID")


def public_metadata(*, sources=None, source=None, source_note=None, fallback=False,
                    degraded=False, citations=None, latency_ms=None, request_id=None):
    """Return the shared metadata shape used by sync, stream, and async APIs."""
    return {
        "source": source,
        "source_note": source_note,
        "fallback": bool(fallback),
        "degraded": bool(degraded),
        "citations": citations or [],
        "sources": list(sources or []),
        "latency_ms": latency_ms,
        "request_id": request_id,
    }

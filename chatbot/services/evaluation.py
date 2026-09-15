"""Small, dependency-free quality checks for municipal AI answer records.

The evaluator is intentionally independent of Django and external providers so
it can score captured responses in unit tests, scripts, or CI.
"""

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping


_ABSTENTION_MARKERS = (
    "i don't have enough information",
    "couldn't reach the ai service",
    "please try again shortly",
    "contact the municipality office directly",
)


@dataclass(frozen=True)
class EvaluationCriteria:
    """Optional expectations for one answer record."""

    expected_abstention: bool = False
    language: str = "en"
    max_latency_ms: float | None = None


def _response(record: Mapping[str, Any]) -> str:
    value = record.get("response", record.get("answer", ""))
    return value.strip() if isinstance(value, str) else ""


def _sources(record: Mapping[str, Any]) -> list[Any]:
    value = record.get("sources", record.get("citations", record.get("source", [])))
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [item for item in value if item]
    return [value] if value else []


def _is_abstention(record: Mapping[str, Any], response: str) -> bool:
    explicit = record.get("abstained", record.get("is_abstention"))
    if explicit is not None:
        return bool(explicit)
    if record.get("source") == "none":
        return True
    lowered = response.lower()
    return any(marker in lowered for marker in _ABSTENTION_MARKERS)


def _language_ok(response: str, language: str) -> bool:
    if not response:
        return False
    language = (language or "en").lower()
    if language.startswith(("ne", "np")):
        return bool(re.search(r"[\u0900-\u097f]", response))
    return bool(re.search(r"[A-Za-z]", response))


def _latency_ms(record: Mapping[str, Any]) -> float | None:
    value = record.get("latency_ms", record.get("latency", record.get("metadata", {}).get("latency_ms")
                                               if isinstance(record.get("metadata"), Mapping) else None))
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def score_record(
    record: Mapping[str, Any],
    criteria: EvaluationCriteria | None = None,
) -> dict[str, Any]:
    """Score one captured answer record using five basic quality signals."""
    criteria = criteria or EvaluationCriteria(
        expected_abstention=bool(record.get("expected_abstention", False)),
        language=str(record.get("language", "en")),
        max_latency_ms=record.get("max_latency_ms"),
    )
    response = _response(record)
    abstained = _is_abstention(record, response)
    latency = _latency_ms(record)

    checks = {
        "non_empty_response": bool(response),
        "grounded_source_present": bool(_sources(record)) if not criteria.expected_abstention else True,
        "abstention_correct": abstained == criteria.expected_abstention and bool(response),
        "language_format_basic": _language_ok(response, criteria.language),
        "latency_metadata_present": latency is not None
        and (criteria.max_latency_ms is None or latency <= criteria.max_latency_ms),
    }
    passed_checks = sum(checks.values())
    return {
        "score": passed_checks / len(checks),
        "passed": passed_checks == len(checks),
        "checks": checks,
        "latency_ms": latency,
        "abstained": abstained,
    }


def score_records(
    records: Iterable[Mapping[str, Any]],
    criteria: EvaluationCriteria | None = None,
) -> dict[str, Any]:
    """Return aggregate baseline metrics for representative answer records."""
    results = [score_record(record, criteria) for record in records]
    count = len(results)
    checks = (
        ("non_empty_response", "non_empty_response"),
        ("grounded_source_presence", "grounded_source_present"),
        ("abstention_correctness", "abstention_correct"),
        ("language_format_basics", "language_format_basic"),
        ("latency_metadata", "latency_metadata_present"),
    )
    rates = {
        name: sum(result["checks"][key] for result in results) / count if count else 0.0
        for name, key in checks
    }
    return {
        "count": count,
        "score": sum(result["score"] for result in results) / count if count else 0.0,
        "passed": sum(result["passed"] for result in results),
        "pass_rate": sum(result["passed"] for result in results) / count if count else 0.0,
        "check_rates": rates,
        "results": results,
    }

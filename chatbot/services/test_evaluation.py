from django.test import SimpleTestCase

from .evaluation import EvaluationCriteria, score_record, score_records


class AnswerEvaluationTests(SimpleTestCase):
    def test_grounded_answer_passes_all_baseline_checks(self):
        result = score_record({
            "response": "Entry fees are NPR 1,500 for foreign visitors.",
            "sources": ["knowledge_base:rules"],
            "latency_ms": 240,
        })

        self.assertTrue(result["passed"])
        self.assertEqual(result["score"], 1.0)

    def test_abstention_does_not_require_a_source(self):
        result = score_record({
            "response": "I don't have enough information for that request.",
            "source": "none",
            "abstained": True,
            "latency_ms": 80,
        }, EvaluationCriteria(expected_abstention=True))

        self.assertTrue(result["checks"]["abstention_correct"])
        self.assertTrue(result["checks"]["grounded_source_present"])

    def test_missing_quality_metadata_is_reported(self):
        result = score_record({"response": "Nyatapola Temple is in Taumadhi Square."})

        self.assertFalse(result["checks"]["grounded_source_present"])
        self.assertFalse(result["checks"]["latency_metadata_present"])
        self.assertFalse(result["passed"])

    def test_nepali_language_and_latency_limit_are_checked(self):
        result = score_record({
            "answer": "न्यातपोल मन्दिर तौमढी स्क्वायरमा छ।",
            "citations": ["faq:heritage"],
            "metadata": {"latency_ms": 600},
        }, EvaluationCriteria(language="ne", max_latency_ms=500))

        self.assertTrue(result["checks"]["language_format_basic"])
        self.assertFalse(result["checks"]["latency_metadata_present"])

    def test_score_records_returns_measurable_aggregate(self):
        summary = score_records([
            {
                "response": "The office is open Sunday to Friday.",
                "sources": ["faq:hours"],
                "latency_ms": 100,
            },
            {
                "response": "I don't have enough information.",
                "source": "none",
                "abstained": True,
                "expected_abstention": True,
                "latency_ms": 90,
            },
        ])

        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["passed"], 2)
        self.assertEqual(summary["pass_rate"], 1.0)
        self.assertIn("check_rates", summary)

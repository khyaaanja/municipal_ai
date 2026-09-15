"""
Tests for the AnswerEngine fallback system.

Coverage:
1. Groq succeeds → source: "groq", degraded: False
2. Groq times out → fallback to local_db, degraded: True
3. Groq rate-limited, fallback_model set → fallback_model, degraded: True
4. Groq fails, no local match / low confidence → source: "none", degraded: True
5. Circuit breaker open → skip Groq, go straight to fallback
6. No local chunks → "none" source with honest message
7. Extractive answer from local chunks
8. Exception during Groq call → fallback
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.core.cache import cache

import httpx
from groq import APIError, APITimeoutError, RateLimitError

from chatbot.services.answer_engine import (
    AnswerEngine,
    LocalRetrieverAdapter,
    LocalChunk,
    is_circuit_open,
    open_circuit,
    is_degraded_response,
    NO_INFO_MESSAGE,
)


# ---------------------------------------------------------------------------
# Helpers to construct real groq exceptions with correct signatures
# ---------------------------------------------------------------------------

def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def _timeout_error() -> APITimeoutError:
    return APITimeoutError(request=_request())


def _api_error(status: int = 500) -> APIError:
    return APIError(
        "Groq API error",
        request=_request(),
        body={"error": {"message": "bad gateway"}},
    )


def _rate_limit_error() -> RateLimitError:
    return RateLimitError(
        "Rate limit exceeded",
        response=httpx.Response(429, request=_request()),
        body={"error": {"message": "rate limited"}},
    )


class FakeChunk:
    """Minimal chunk duck-typing for tests."""

    def __init__(self, text, score, title=''):
        self.text = text
        self.score = score
        self.title = title


class MockRetriever:
    """Retriever that returns predefined chunks."""

    def __init__(self, chunks=None):
        self.chunks = chunks or []

    def retrieve(self, query, top_k=5):
        return self.chunks[:top_k]


class FakeFallbackModel:
    """Simulated lightweight fallback model."""

    def __init__(self, response='Fallback model answer'):
        self.response = response

    def generate(self, query, chunks):
        return self.response


class AnswerEngineTestBase(TestCase):
    """Base class that clears the circuit breaker cache between tests."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()


class AnswerEngineSuccessTests(AnswerEngineTestBase):
    """1. Groq succeeds → source: "groq", degraded: False"""

    def test_groq_success_returns_groq_source(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content='Nyatapola Temple is located in Taumadhi Square.'))
        ]

        retriever = MockRetriever([
            FakeChunk('Nyatapola Temple is a five-storey pagoda in Taumadhi Square.', 0.85)
        ])

        engine = AnswerEngine(groq_client=mock_client, retriever=retriever, api_key='test-key')
        result = engine.answer('Where is Nyatapola Temple?')

        self.assertEqual(result['source'], 'groq')
        self.assertFalse(result['degraded'])
        self.assertIn('Nyatapola', result['answer'])
        # Verify Groq was called
        mock_client.chat.completions.create.assert_called_once()

    def test_groq_success_without_local_chunks(self):
        """Even without local chunks, Groq success should return groq source."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content='General answer from AI.'))
        ]

        engine = AnswerEngine(groq_client=mock_client, retriever=MockRetriever([]), api_key='test-key')
        result = engine.answer('Tell me about Bhaktapur')

        self.assertEqual(result['source'], 'groq')
        self.assertFalse(result['degraded'])
        self.assertIn('General answer', result['answer'])


class AnswerEngineTimeoutTests(AnswerEngineTestBase):
    """2. Groq times out → fallback to local_db, degraded: True"""

    def test_groq_timeout_falls_to_local_db(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _timeout_error()

        retriever = MockRetriever([
            FakeChunk('Nyatapola Temple is a five-storey pagoda in Taumadhi Square, Bhaktapur.', 0.85),
            FakeChunk('Entry fee for Nyatapola Temple is included in the Durbar Square ticket.', 0.70),
        ])

        engine = AnswerEngine(groq_client=mock_client, retriever=retriever, api_key='test-key')
        result = engine.answer('Where is Nyatapola Temple?')

        self.assertEqual(result['source'], 'local_db')
        self.assertTrue(result['degraded'])
        self.assertIn('Nyatapola', result['answer'])
        # Circuit breaker should be open
        self.assertTrue(is_circuit_open())

    def test_groq_timeout_opens_circuit_breaker(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _timeout_error()

        engine = AnswerEngine(
            groq_client=mock_client,
            retriever=MockRetriever([FakeChunk('Some info.', 0.85)]),
            api_key='test-key',
        )
        self.assertFalse(is_circuit_open())
        engine.answer('Test query')
        self.assertTrue(is_circuit_open())


class AnswerEngineRateLimitTests(AnswerEngineTestBase):
    """3. Groq rate-limited, fallback_model set → fallback_model, degraded: True"""

    def test_rate_limit_with_fallback_model(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _rate_limit_error()

        retriever = MockRetriever([
            FakeChunk('Bhaktapur Durbar Square is a UNESCO World Heritage Site.', 0.90),
        ])

        fallback_model = FakeFallbackModel('Bhaktapur Durbar Square is a historic royal palace complex.')

        engine = AnswerEngine(
            groq_client=mock_client,
            retriever=retriever,
            fallback_model=fallback_model,
            api_key='test-key',
        )
        result = engine.answer('Tell me about Durbar Square')

        self.assertEqual(result['source'], 'fallback_model')
        self.assertTrue(result['degraded'])
        self.assertIn('Bhaktapur Durbar Square', result['answer'])

    def test_rate_limit_without_fallback_model(self):
        """Without fallback model, it should fall through to extractive."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _rate_limit_error()

        retriever = MockRetriever([
            FakeChunk('Bhaktapur Durbar Square is a UNESCO World Heritage Site.', 0.90),
        ])

        engine = AnswerEngine(groq_client=mock_client, retriever=retriever, api_key='test-key')
        result = engine.answer('Tell me about Durbar Square')

        self.assertEqual(result['source'], 'local_db')
        self.assertTrue(result['degraded'])
        self.assertIn('UNESCO', result['answer'])


class AnswerEngineNoLocalMatchTests(AnswerEngineTestBase):
    """4. Groq fails, no local match / low confidence → source: "none", degraded: True"""

    def test_groq_fails_no_local_chunks(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _api_error()

        engine = AnswerEngine(groq_client=mock_client, retriever=MockRetriever([]), api_key='test-key')
        result = engine.answer('What is the meaning of life?')

        self.assertEqual(result['source'], 'none')
        self.assertTrue(result['degraded'])
        self.assertEqual(result['answer'], NO_INFO_MESSAGE)

    def test_groq_fails_low_confidence_chunks(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _api_error()

        retriever = MockRetriever([
            FakeChunk('Some marginally relevant information.', 0.10),
        ])

        engine = AnswerEngine(
            groq_client=mock_client,
            retriever=retriever,
            confidence_threshold=0.30,
            api_key='test-key',
        )
        result = engine.answer('Random query')

        self.assertEqual(result['source'], 'none')
        self.assertTrue(result['degraded'])
        self.assertEqual(result['answer'], NO_INFO_MESSAGE)


class AnswerEngineCircuitBreakerTests(AnswerEngineTestBase):
    """5. Circuit breaker open → skip Groq, go straight to fallback"""

    def test_circuit_breaker_skips_groq(self):
        mock_client = MagicMock()
        retriever = MockRetriever([
            FakeChunk('Bhaktapur is known for its Newari architecture.', 0.80),
        ])

        # Open circuit breaker first
        open_circuit()

        engine = AnswerEngine(groq_client=mock_client, retriever=retriever, api_key='test-key')
        result = engine.answer('What is Bhaktapur known for?')

        # Groq should NOT have been called
        mock_client.chat.completions.create.assert_not_called()
        self.assertEqual(result['source'], 'local_db')
        self.assertTrue(result['degraded'])
        self.assertIn('Newari', result['answer'])

    def test_circuit_breaker_skips_groq_low_confidence(self):
        """When circuit is open AND no confident match, return 'none' source."""
        open_circuit()

        mock_client = MagicMock()
        retriever = MockRetriever([
            FakeChunk('Low confidence irrelevant info.', 0.05),
        ])

        engine = AnswerEngine(
            groq_client=mock_client,
            retriever=retriever,
            confidence_threshold=0.30,
            api_key='test-key',
        )
        result = engine.answer('Something obscure')

        mock_client.chat.completions.create.assert_not_called()
        self.assertEqual(result['source'], 'none')
        self.assertTrue(result['degraded'])
        self.assertEqual(result['answer'], NO_INFO_MESSAGE)

    def test_circuit_breaker_does_not_skip_when_closed(self):
        """When circuit breaker is closed, Groq should be called."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content='Normal Groq response.'))
        ]

        retriever = MockRetriever([
            FakeChunk('Some context.', 0.80),
        ])

        engine = AnswerEngine(groq_client=mock_client, retriever=retriever, api_key='test-key')
        result = engine.answer('Normal query')

        mock_client.chat.completions.create.assert_called_once()
        self.assertEqual(result['source'], 'groq')
        self.assertFalse(result['degraded'])

    def test_circuit_breaker_auto_resets_after_timeout(self):
        """Circuit breaker should auto-reset after CIRCUIT_TIMEOUT seconds."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content='Recovered response.'))
        ]

        retriever = MockRetriever([
            FakeChunk('Some context.', 0.80),
        ])

        # Open circuit with 1s timeout
        open_circuit(timeout=1)
        self.assertTrue(is_circuit_open())

        # Wait for it to expire
        import time
        time.sleep(1.1)

        engine = AnswerEngine(
            groq_client=mock_client,
            retriever=retriever,
            circuit_timeout=1,
            api_key='test-key',
        )
        result = engine.answer('Recovered query')

        # Groq should be called again since circuit is closed
        mock_client.chat.completions.create.assert_called_once()
        self.assertEqual(result['source'], 'groq')
        self.assertFalse(result['degraded'])


class AnswerEngineExtractiveTests(AnswerEngineTestBase):
    """7. Extractive answer from local chunks"""

    def test_extractive_answer_includes_top_chunk(self):
        """The extractive answer should include the text of the top chunk."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _api_error()

        retriever = MockRetriever([
            FakeChunk("Bhaktapur's Pottery Square is where traditional pottery is made.", 0.80),
        ])

        engine = AnswerEngine(groq_client=mock_client, retriever=retriever, api_key='test-key')
        result = engine.answer('Tell me about Pottery Square')

        self.assertEqual(result['source'], 'local_db')
        self.assertTrue(result['degraded'])
        self.assertIn('Pottery Square', result['answer'])
        self.assertIn('municipal records', result['answer'])

    def test_extractive_answer_with_title(self):
        """When chunks have a title, it should appear in the answer."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _api_error()

        retriever = MockRetriever([
            FakeChunk('Entry fee: NPR 1,500 for foreigners.', 0.85, 'Entry Fees'),
        ])

        engine = AnswerEngine(groq_client=mock_client, retriever=retriever, api_key='test-key')
        result = engine.answer('What is the entry fee?')

        self.assertIn('Entry Fees', result['answer'])
        self.assertIn('NPR 1,500', result['answer'])

    def test_extractive_answer_with_multiple_chunks(self):
        """Multiple chunks should include related information section."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _api_error()

        retriever = MockRetriever([
            FakeChunk('Nyatapola Temple is a five-storey pagoda.', 0.85, 'Nyatapola Temple'),
            FakeChunk('It was built in 1702 during King Bhupatindra Malla reign.', 0.75, 'History'),
            FakeChunk('It is located in Taumadhi Square.', 0.70, 'Location'),
        ])

        engine = AnswerEngine(groq_client=mock_client, retriever=retriever, api_key='test-key')
        result = engine.answer('Tell me about Nyatapola')

        self.assertIn('Nyatapola', result['answer'])
        self.assertIn('Related information', result['answer'])


class AnswerEngineExceptionTests(AnswerEngineTestBase):
    """8. Exception during Groq call → fallback"""

    def test_generic_exception_during_groq_call(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ConnectionError('Network is unreachable')

        retriever = MockRetriever([
            FakeChunk('Bhaktapur is a UNESCO World Heritage City.', 0.85),
        ])

        engine = AnswerEngine(groq_client=mock_client, retriever=retriever, api_key='test-key')
        result = engine.answer('Tell me about Bhaktapur')

        self.assertEqual(result['source'], 'local_db')
        self.assertTrue(result['degraded'])
        self.assertIn('UNESCO', result['answer'])

    def test_no_groq_client_no_api_key(self):
        """Without Groq client or API key, should go straight to fallback."""
        retriever = MockRetriever([
            FakeChunk('Bhaktapur is known for its rich culture.', 0.80),
        ])

        engine = AnswerEngine(groq_client=None, retriever=retriever, api_key='')
        result = engine.answer('Tell me about Bhaktapur')

        self.assertEqual(result['source'], 'local_db')
        self.assertTrue(result['degraded'])

    def test_empty_response_from_groq(self):
        """If Groq returns empty content, treat as failure."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=''))
        ]

        retriever = MockRetriever([
            FakeChunk('Bhaktapur Durbar Square is a UNESCO site.', 0.85),
        ])

        engine = AnswerEngine(groq_client=mock_client, retriever=retriever, api_key='test-key')
        result = engine.answer('Tell me about Durbar Square')

        self.assertEqual(result['source'], 'local_db')
        self.assertTrue(result['degraded'])


class AnswerEngineRetrieverAdapterTests(TestCase):
    """Tests for LocalRetrieverAdapter."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_retriever_adapter_returns_local_chunks(self):
        adapter = LocalRetrieverAdapter()
        with patch.object(adapter.retriever, 'retrieve', return_value={
            'kb:search': [{'title': 'Test', 'content': 'Test content about Bhaktapur.'}],
        }):
            chunks = adapter.retrieve('test query')
            self.assertGreater(len(chunks), 0)
            self.assertIsInstance(chunks[0], LocalChunk)
            self.assertIn('Test content', chunks[0].text)

    def test_retriever_adapter_empty_data(self):
        adapter = LocalRetrieverAdapter()
        with patch.object(adapter.retriever, 'retrieve', return_value={}):
            chunks = adapter.retrieve('test query')
            self.assertEqual(len(chunks), 0)

    def test_retriever_adapter_deduplication(self):
        """Duplicate texts should be removed."""
        city_data = {
            'kb:search': [
                {'title': 'A', 'content': 'Same content'},
                {'title': 'B', 'content': 'Same content'},
            ],
        }
        chunks = LocalRetrieverAdapter.chunks_from_city_data(city_data, top_k=5)
        # Only one of the two should remain
        self.assertEqual(len(chunks), 1)

    def test_retriever_adapter_structured_data(self):
        """Structured data (attractions, events) should be converted to text."""
        city_data = {
            'attractions': [
                {'name': 'Nyatapola Temple', 'description': 'Five-storey pagoda', 'entry_fee': 'NPR 1,500'},
            ],
        }
        chunks = LocalRetrieverAdapter.chunks_from_city_data(city_data, top_k=5)
        self.assertGreater(len(chunks), 0)
        text = chunks[0].text
        self.assertIn('Nyatapola', text)
        self.assertIn('NPR 1,500', text)


class IsDegradedResponseTests(TestCase):
    """Tests for the is_degraded_response heuristic."""

    def test_degraded_markers_detected(self):
        self.assertTrue(is_degraded_response("I'm having trouble connecting right now"))
        self.assertTrue(is_degraded_response("I'm having trouble responding right now"))
        self.assertTrue(is_degraded_response("I'm a little busy right now"))
        self.assertTrue(is_degraded_response("I've hit my response limit"))
        self.assertTrue(is_degraded_response("Groq error: something went wrong"))
        self.assertTrue(is_degraded_response("Please try again in a moment"))

    def test_normal_responses_not_degraded(self):
        self.assertFalse(is_degraded_response("Nyatapola Temple is located in Taumadhi Square."))
        self.assertFalse(is_degraded_response("The entry fee is NPR 1,500 for foreigners."))
        self.assertFalse(is_degraded_response(""))
        self.assertFalse(is_degraded_response("Hello! Welcome to Bhaktapur."))


class AnswerEngineConfigTests(AnswerEngineTestBase):
    """Test that configurable parameters work correctly."""

    def test_custom_circuit_timeout(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _api_error()

        engine = AnswerEngine(
            groq_client=mock_client,
            retriever=MockRetriever([FakeChunk('Info.', 0.85)]),
            circuit_timeout=120,
            api_key='test-key',
        )
        engine.answer('Test')

        # Circuit should be open
        self.assertTrue(is_circuit_open())

    def test_custom_confidence_threshold(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _api_error()

        # High threshold (0.90) — our 0.85 chunk should be rejected
        engine = AnswerEngine(
            groq_client=mock_client,
            retriever=MockRetriever([FakeChunk('Info.', 0.85)]),
            confidence_threshold=0.90,
            api_key='test-key',
        )
        result = engine.answer('Test')
        self.assertEqual(result['source'], 'none')

    def test_low_confidence_threshold(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _api_error()

        # Low threshold (0.20) — our 0.85 chunk should be accepted
        engine = AnswerEngine(
            groq_client=mock_client,
            retriever=MockRetriever([FakeChunk('Info.', 0.85)]),
            confidence_threshold=0.20,
            api_key='test-key',
        )
        result = engine.answer('Test')
        self.assertEqual(result['source'], 'local_db')


class AnswerEngineFallbackModelFailureTests(AnswerEngineTestBase):
    """When fallback model is set but also fails, fall through to extractive."""

    def test_fallback_model_raises_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _rate_limit_error()

        retriever = MockRetriever([
            FakeChunk('Bhaktapur is known for its culture.', 0.85),
        ])

        class BrokenFallbackModel:
            def generate(self, query, chunks):
                raise RuntimeError('Fallback model crashed')

        engine = AnswerEngine(
            groq_client=mock_client,
            retriever=retriever,
            fallback_model=BrokenFallbackModel(),
            api_key='test-key',
        )
        result = engine.answer('Tell me about Bhaktapur')

        # Should fall through to extractive
        self.assertEqual(result['source'], 'local_db')
        self.assertTrue(result['degraded'])
        self.assertIn('culture', result['answer'])


from unittest.mock import patch
import json

from django.test import TestCase
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from accounts.models import User
from .ai_engine import MunicipalAIEngine
from .tasks import process_chat_async
from .models import Conversation, Message
from complaints.models import Complaint
from core.utils import parse_structured_json
from core.utils import MAX_AI_AUDIO_BYTES


def make_user(email='bot@test.com'):
    return User.objects.create_user(
        email=email, username=email.split('@')[0],
        password='Pass1234!', first_name='C', last_name='U'
    )


class ChatbotPageTests(TestCase):
    def test_chat_page_loads_anonymous(self):
        r = self.client.get('/chat/')
        self.assertEqual(r.status_code, 200)

    def test_chat_page_loads_logged_in(self):
        make_user()
        self.client.login(username='bot@test.com', password='Pass1234!')
        r = self.client.get('/chat/')
        self.assertEqual(r.status_code, 200)

    def test_history_requires_login(self):
        r = self.client.get('/chat/history/')
        self.assertEqual(r.status_code, 302)

    def test_history_loads_when_logged_in(self):
        make_user()
        self.client.login(username='bot@test.com', password='Pass1234!')
        r = self.client.get('/chat/history/')
        self.assertEqual(r.status_code, 200)


class AIResponseFallbackTests(TestCase):
    def setUp(self):
        MunicipalAIEngine._instance = None
        MunicipalAIEngine._initialized = False

    @patch('chatbot.ai_engine.MunicipalAIEngine._get_cached_city_data', return_value=({}, ''))
    @patch('chatbot.ai_engine.MunicipalAIEngine._call_groq', return_value='')
    def test_empty_model_response_is_replaced_with_local_answer(self, _call_groq, _context):
        with patch('chatbot.ai_engine.MunicipalAIEngine._maybe_auto_save_kb'), \
             patch('chatbot.ai_engine.MunicipalAIEngine._update_user_profile'):
            result = MunicipalAIEngine().chat('What is the entry fee?')

        self.assertTrue(result['response'].strip())
        self.assertIn('Entry Fees', result['response'])

    @patch('chatbot.ai_engine.MunicipalAIEngine._get_cached_city_data', return_value=({}, ''))
    def test_stream_without_api_key_uses_local_answer(self, _context):
        engine = MunicipalAIEngine()
        engine.api_key = ''

        events = list(engine.build_stream('What is the entry fee?'))
        tokens = ''.join(payload for kind, payload in events if kind == 'token')

        self.assertTrue(tokens.strip())
        self.assertIn('Entry Fees', tokens)

    def test_fallback_abstains_for_unrelated_question(self):
        engine = MunicipalAIEngine()

        response = engine._fallback_response(
            'What is the meaning of life?',
            {'attractions': [{'name': 'Nyatapola Temple'}]},
        )

        self.assertIn("don't have enough reliable information", response)

    def test_fallback_prefers_query_relevant_knowledge_entry(self):
        engine = MunicipalAIEngine()

        response = engine._fallback_response(
            'Where is Nyatapola Temple?',
            {
                'kb:heritage': [
                    {'title': 'Bhaktapur Durbar Square', 'content': 'A royal palace complex.'},
                    {'title': 'Nyatapola Temple', 'content': 'It stands in Taumadhi Square.'},
                ],
            },
        )

        self.assertIn('Nyatapola Temple', response)
        self.assertIn('Taumadhi Square', response)

    def test_context_cache_is_query_specific(self):
        from django.core.cache import cache
        cache.clear()
        engine = MunicipalAIEngine()
        with patch.object(engine.retriever, 'retrieve', side_effect=[
            {'kb:heritage': [{'title': 'Nyatapola', 'content': 'Taumadhi Square'}]},
            {'kb:rules': [{'title': 'Entry fees', 'content': 'NPR 1500'}]},
        ]) as retrieve:
            first, _ = engine._get_cached_city_data('Where is Nyatapola?', 'tourism', compact=True)
            second, _ = engine._get_cached_city_data('What is the entry fee?', 'tourism', compact=True)

        self.assertNotEqual(first, second)
        self.assertEqual(retrieve.call_count, 2)

    def test_compact_context_keeps_query_specific_records(self):
        engine = MunicipalAIEngine()
        context = engine.build_context_prompt(
            {'attractions': [{
                'name': 'Nyatapola Temple',
                'category': 'Heritage',
                'description': 'A five-story temple.',
                'entry_fee': 'NPR 500',
                'opening_hours': '6 AM-6 PM',
                'address': 'Taumadhi Square',
            }]},
            compact=True,
        )
        self.assertIn('Nyatapola Temple', context)
        self.assertIn('6 AM-6 PM', context)

    def test_devanagari_language_detection_distinguishes_hindi_and_nepali(self):
        self.assertEqual(MunicipalAIEngine._detect_language('मंदिर का प्रवेश शुल्क कितना है?'), 'hi')
        self.assertEqual(MunicipalAIEngine._detect_language('मन्दिरको प्रवेश शुल्क कति हो?'), 'ne')

    def test_intent_prioritizes_transport_for_hotel_directions(self):
        self.assertEqual(
            MunicipalAIEngine()._detect_intent('How do I get to the hotel?'),
            'transport',
        )

    def test_fallback_answers_restaurant_query_from_restaurant_records(self):
        engine = MunicipalAIEngine()
        response = engine._fallback_response(
            'Is there a restaurant near the temple?',
            {
                'restaurants': [{
                    'name': 'Peacock Restaurant',
                    'description': 'Newari cuisine',
                    'address': 'Durbar Square',
                }],
                'kb:heritage': [{
                    'title': 'Nyatapola Temple',
                    'content': 'A temple near the square.',
                }],
            },
        )
        self.assertIn('Peacock Restaurant', response)
        self.assertNotIn('Nyatapola Temple', response)

    def test_unrelated_weather_query_abstains(self):
        engine = MunicipalAIEngine()
        response = engine._fallback_response(
            'What is the weather tomorrow?',
            {'kb:semantic': [{
                'title': 'Thangka Painting Tradition',
                'content': 'A cultural painting tradition.',
            }]},
        )
        self.assertIn("don't have enough reliable information", response)

    def test_direction_query_uses_transport_fallback(self):
        response = MunicipalAIEngine()._fallback_response(
            'How do I get to the hotel?',
            {'kb:transport': [{
                'title': 'Getting Around',
                'content': 'Bus and taxi information.',
            }]},
        )
        self.assertIn('Bus No.1', response)
        self.assertNotIn('About Bhaktapur', response)

    def test_hotel_query_uses_accommodation_records(self):
        response = MunicipalAIEngine()._fallback_response(
            'What hotels are near Durbar Square?',
            {'hotels': [{
                'name': 'Bhadgaon Guest House',
                'address': 'Durbar Square, Bhaktapur',
            }]},
        )
        self.assertIn('Bhadgaon Guest House', response)

    def test_shopping_query_lists_local_products(self):
        response = MunicipalAIEngine()._fallback_response(
            'What souvenirs can I buy?',
            {'products': [{
                'name': 'Singing Bowl',
                'price': 1800,
            }]},
        )
        self.assertIn('Singing Bowl', response)
        self.assertIn('NPR 1800', response)

    def test_services_query_does_not_return_unrelated_city_description(self):
        response = MunicipalAIEngine()._fallback_response(
            'What services does the municipality provide?',
            {},
        )
        self.assertIn('Municipal Services', response)
        self.assertIn('Complaint reporting', response)
        self.assertNotIn('known locally as Khwopa', response)

    def test_localized_fee_queries_answer_in_detected_language(self):
        engine = MunicipalAIEngine()
        hindi = engine._fallback_response('मंदिर का प्रवेश शुल्क कितना है?', {})
        nepali = engine._fallback_response('मन्दिरको प्रवेश शुल्क कति हो?', {})
        self.assertIn('विदेशी नागरिक', hindi)
        self.assertIn('विदेशी नागरिक', nepali)

    @patch('chatbot.ai_engine._get_groq_client')
    def test_stream_failure_does_not_emit_partial_model_answer(self, get_client):
        class BrokenStream:
            def __iter__(self):
                yield type('Chunk', (), {
                    'choices': [type('Choice', (), {
                        'delta': type('Delta', (), {'content': 'partial answer'})()
                    })()]
                })()
                raise RuntimeError('stream disconnected')

        get_client.return_value.chat.completions.create.return_value = BrokenStream()
        engine = MunicipalAIEngine()
        engine.api_key = 'test-key'
        with patch.object(engine, '_fallback_response', return_value='local answer'):
            events = list(engine.build_stream('What is the entry fee?'))
        tokens = [payload for kind, payload in events if kind == 'token']
        self.assertEqual(tokens, ['local answer'])

    def test_structured_json_parser_rejects_malformed_provider_output(self):
        self.assertEqual(parse_structured_json('not json'), {})
        self.assertEqual(parse_structured_json('{"category": "ROAD"}'), {'category': 'ROAD'})

    @patch('chatbot.ai_engine._get_groq_client')
    def test_complaint_categorization_filters_invalid_provider_values(self, get_client):
        get_client.return_value.chat.completions.create.return_value.choices = [
            type('Choice', (), {
                'message': type('Message', (), {
                    'content': '{"category": "MADE_UP", "priority": "urgent", "ward": 99}'
                })()
            })()
        ]
        engine = MunicipalAIEngine()
        engine.api_key = 'test-key'
        self.assertEqual(engine.categorize_complaint('title', 'description'), {'priority': 'urgent'})

    def test_voice_rejects_oversized_audio(self):
        upload = SimpleUploadedFile(
            'voice.webm', b'x' * (MAX_AI_AUDIO_BYTES + 1), content_type='audio/webm'
        )
        response = self.client.post('/api/voice/', {'audio': upload})
        self.assertEqual(response.status_code, 400)

    def test_engine_image_scan_rejects_invalid_input(self):
        engine = MunicipalAIEngine()
        self.assertIn('valid image', engine.analyze_image('not-base64'))


class AsyncAutosaveIsolationTests(TestCase):
    @patch('chatbot.tasks.auto_save_kb_entry.delay', side_effect=RuntimeError('broker unavailable'))
    @patch('chatbot.ai_engine.MunicipalAIEngine')
    def test_autosave_enqueue_failure_keeps_completed_result(self, mock_engine, _enqueue):
        mock_engine.return_value.chat.return_value = {
            'response': 'A completed answer',
            'sources': ['knowledge_base'],
            'intent': 'tourism',
            'followups': [],
        }

        process_chat_async.run('autosave-test', 'Where is the temple?', [], None, None, 'session')

        payload = json.loads(cache.get('chat_job:autosave-test'))
        self.assertEqual(payload['status'], 'done')
        self.assertEqual(payload['response'], 'A completed answer')

    def test_async_complaint_lookup_does_not_disclose_foreign_record(self):
        owner = make_user('owner@test.com')
        complaint = Complaint.objects.create(
            user=owner,
            category='ROAD',
            title='Private road issue',
            description='Private details',
            location='Ward 1',
            submitter_name='Owner',
        )

        process_chat_async.run(
            'private-status-test',
            f'What is the status of {complaint.complaint_id}?',
            [],
            None,
            None,
            'different-session',
        )

        payload = json.loads(cache.get('chat_job:private-status-test'))
        self.assertEqual(payload['status'], 'done')
        self.assertNotIn('Private road issue', payload['response'])
        self.assertIn('privacy', payload['response'].lower())


class ResponseContractRegressionTests(TestCase):
    @patch('chatbot.views.MunicipalAIEngine.build_stream')
    def test_stream_done_event_contains_shared_metadata(self, build_stream):
        build_stream.return_value = iter([
            ('token', 'A streamed answer'),
            ('meta', {
                'intent': 'tourism',
                'sources': ['knowledge_base'],
                'followups': [],
                'source': 'fallback',
                'source_note': 'Answered from local records',
                'fallback': True,
                'degraded': True,
                'citations': [{'title': 'FAQ'}],
            }),
        ])

        response = self.client.post(
            '/api/chat/stream/',
            data=json.dumps({'message': 'Where is the temple?'}),
            content_type='application/json',
        )
        events = b''.join(response.streaming_content).decode()
        self.assertIn('"source": "fallback"', events)
        self.assertIn('"citations": [{"title": "FAQ"}]', events)
        self.assertEqual(Message.objects.filter(role=Message.ROLE_ASSISTANT).count(), 1)

    @patch('chatbot.tasks.auto_save_kb_entry.delay')
    @patch('chatbot.ai_engine.MunicipalAIEngine')
    def test_async_blank_response_is_not_persisted(self, mock_engine, _autosave):
        mock_engine.return_value.chat.return_value = {
            'response': '   ',
            'sources': ['knowledge_base'],
            'intent': 'general',
            'followups': [],
            'source': 'fallback',
            'fallback': True,
            'degraded': True,
            'citations': [],
        }

        process_chat_async.run('blank-response-test', 'Question?', [], None, None, 'session')

        payload = json.loads(cache.get('chat_job:blank-response-test'))
        self.assertEqual(payload['status'], 'done')
        self.assertIsNone(payload['message_id'])
        self.assertFalse(Message.objects.filter(role=Message.ROLE_ASSISTANT).exists())
        self.assertEqual(payload['source'], 'fallback')

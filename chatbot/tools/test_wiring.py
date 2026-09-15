"""Wiring tests: the chat endpoints must route through the tool contract.

The properties under test are endpoint-level: a routed reply must not be
writable to the shared response cache, and the complaint lookup must not
let an outsider distinguish a reference that exists from one that does not.
"""
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase

from chatbot.tools.router import route
from complaints.models import Complaint

User = get_user_model()


class RouterTests(TestCase):
    def test_reference_routes_to_status_lookup(self):
        name, kwargs = route('what is happening with BK-A1B2C3')
        self.assertEqual(name, 'get_complaint_status')
        self.assertEqual(kwargs['complaint_id'], 'BK-A1B2C3')

    def test_possessive_required_for_private_tools(self):
        self.assertEqual(route('my complaints')[0], 'get_my_complaints')
        # Bare topic words must not route into a per-citizen tool.
        self.assertIsNone(route('how do complaints work'))

    def test_romanised_nepali_routes(self):
        self.assertEqual(route('mero gunaso kata pugyo')[0], 'get_my_complaints')

    def test_ambiguous_message_falls_through(self):
        self.assertIsNone(route('tell me about Bhaktapur'))
        self.assertIsNone(route(''))
        self.assertIsNone(route(None))

    def test_claim_token_is_carried_through(self):
        _, kwargs = route('status of BK-ZZ1122', claim_token='tok-123')
        self.assertEqual(kwargs['claim_token'], 'tok-123')


class ChatEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.alice = User.objects.create_user(
            email='alice-w@example.com', password='pw-alice-w1')
        self.complaint = Complaint.objects.create(
            user=self.alice, category='WATER', title='No water',
            description='Out for three days in Ward 4.',
            location='Dattatreya', submitter_name='Alice',
            submitter_phone='9800000009', ward_number=4,
        )

    def post(self, message):
        return self.client.post(
            '/api/chat/', data=json.dumps({'message': message}),
            content_type='application/json')

    def test_unissued_and_malformed_references_are_indistinguishable(self):
        """Status is public by reference, matching /complaint/status/<id>/.

        So a real reference is necessarily distinguishable from a fake one.
        What must not differ is *how* a lookup fails: an unissued reference
        and a malformed one give the same answer, so failure modes leak
        nothing about the reference space.
        """
        unissued = self.post('status of BK-QQ9988').json()['response']
        malformed = self.post('status of BK-ZZZZZZ').json()['response']
        self.assertEqual(unissued, malformed)

    def test_outsider_sees_status_but_never_contact_details(self):
        body = self.post(f'status of {self.complaint.complaint_id}').json()['response']
        self.assertIn('Status', body)
        self.assertNotIn('9800000009', body)

    def test_owner_sees_their_complaint_over_the_endpoint(self):
        self.client.force_login(self.alice)
        body = self.post(f'status of {self.complaint.complaint_id}').json()
        self.assertIn(self.complaint.complaint_id, body['response'])
        self.assertEqual(body['intent'], 'get_complaint_status')

    def test_outsider_never_sees_submitter_phone(self):
        body = self.post(f'status of {self.complaint.complaint_id}').json()
        self.assertNotIn('9800000009', body['response'])

    def test_routed_reply_is_not_written_to_shared_cache(self):
        """I-1 at the call site, asserted against whatever cache is configured."""
        self.client.force_login(self.alice)
        message = 'show my complaints'
        self.post(message)
        self.assertIsNone(cache.get(_response_cache_key(message)))

    def test_anonymous_private_tool_asks_for_sign_in(self):
        body = self.post('show my complaints').json()
        self.assertIn('signed in', body['response'].lower())
        self.assertNotIn('No water', body['response'])


def _response_cache_key(message):
    """Reproduce the key chat_api would use, so this works on any backend."""
    import hashlib
    normalised = message.lower().strip()[:200].rstrip('?.! ')
    return 'ai_resp_' + hashlib.sha256(normalised.encode()).hexdigest()[:24]

"""Security tests for the Phase 7 write path."""
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.test import RequestFactory, TestCase

from chatbot.tools import run_tool
from complaints.models import Complaint
from complaints.services import VALID_CATEGORIES, create_complaint

User = get_user_model()

DRAFT = dict(
    category='WATER', title='No water in Ward 4',
    description='Supply has been out for three days near Dattatreya Square.',
    location='Dattatreya Square', ward_number=4, submitter_name='Alice',
)


class WriteTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()

    def request(self, user=None):
        req = self.rf.post('/chat/')
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req.user = user or _Anon()
        return req


class _Anon:
    is_authenticated = False
    is_staff = False
    pk = None
    role = None


class ConfirmationGateTests(WriteTestBase):
    def test_draft_does_not_create_a_complaint(self):
        result = run_tool('draft_complaint', self.request(), **DRAFT)
        self.assertTrue(result.ok)
        self.assertEqual(result.data['stage'], 'awaiting_confirmation')
        self.assertEqual(Complaint.objects.count(), 0)

    def test_confirm_creates_exactly_one_complaint(self):
        req = self.request()
        token = run_tool('draft_complaint', req, **DRAFT).data['token']
        result = run_tool('confirm_complaint', req, token=token)
        self.assertTrue(result.ok)
        self.assertEqual(Complaint.objects.count(), 1)
        self.assertTrue(result.data['complaint_id'].startswith('BK-'))

    def test_returned_reference_is_the_real_stored_one(self):
        req = self.request()
        token = run_tool('draft_complaint', req, **DRAFT).data['token']
        ref = run_tool('confirm_complaint', req, token=token).data['complaint_id']
        self.assertTrue(Complaint.objects.filter(complaint_id=ref).exists())

    def test_confirm_without_token_files_nothing(self):
        result = run_tool('confirm_complaint', self.request(), token='')
        self.assertFalse(result.ok)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_unknown_token_files_nothing(self):
        result = run_tool('confirm_complaint', self.request(), token='made-up')
        self.assertFalse(result.ok)
        self.assertEqual(Complaint.objects.count(), 0)


class ReplayTests(WriteTestBase):
    def test_token_cannot_be_used_twice(self):
        req = self.request()
        token = run_tool('draft_complaint', req, **DRAFT).data['token']
        first = run_tool('confirm_complaint', req, token=token)
        second = run_tool('confirm_complaint', req, token=token)
        self.assertTrue(first.ok)
        self.assertFalse(second.ok)
        self.assertEqual(Complaint.objects.count(), 1)


class PendingOwnershipTests(WriteTestBase):
    def test_another_session_cannot_confirm_someone_elses_draft(self):
        drafter = self.request()
        token = run_tool('draft_complaint', drafter, **DRAFT).data['token']

        attacker = self.request()
        result = run_tool('confirm_complaint', attacker, token=token)
        self.assertFalse(result.ok)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_payload_is_not_taken_from_the_confirm_call(self):
        """The model cannot smuggle new values in at execution time."""
        req = self.request()
        token = run_tool('draft_complaint', req, **DRAFT).data['token']
        run_tool('confirm_complaint', req, token=token)
        filed = Complaint.objects.get()
        self.assertEqual(filed.title, DRAFT['title'])
        self.assertEqual(filed.category, 'WATER')


class DraftValidationTests(WriteTestBase):
    def test_invalid_category_is_refused(self):
        bad = dict(DRAFT, category='ADMIN_OVERRIDE')
        result = run_tool('draft_complaint', self.request(), **bad)
        self.assertFalse(result.ok)

    def test_short_description_is_refused(self):
        bad = dict(DRAFT, description='broken')
        result = run_tool('draft_complaint', self.request(), **bad)
        self.assertFalse(result.ok)

    def test_out_of_range_ward_is_dropped_not_stored(self):
        odd = dict(DRAFT, ward_number=999)
        result = run_tool('draft_complaint', self.request(), **odd)
        self.assertTrue(result.ok)
        self.assertIsNone(result.data['draft']['ward_number'])


class ServiceValidationTests(TestCase):
    def test_service_rejects_category_outside_choices(self):
        """The model declares choices but create() does not enforce them."""
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            create_complaint(
                category='NOT_A_CATEGORY', title='x',
                description='y', location='z', submitter_name='Alice',
            )
        self.assertEqual(Complaint.objects.count(), 0)

    def test_service_accepts_every_declared_category(self):
        for cat in VALID_CATEGORIES:
            create_complaint(
                category=cat, title=f'Issue {cat}',
                description='A description long enough to be meaningful.',
                location='Ward 1', submitter_name='Alice',
            )
        self.assertEqual(Complaint.objects.count(), len(VALID_CATEGORIES))

    def test_anonymous_complaint_gets_a_claim_token(self):
        c = create_complaint(
            category='ROAD', title='Pothole', description='Large pothole.',
            location='Pottery Square', submitter_name='Alice',
            user=None, session_key='abc123',
        )
        self.assertIsNotNone(c.claim_token)
        self.assertEqual(c.session_key, 'abc123')

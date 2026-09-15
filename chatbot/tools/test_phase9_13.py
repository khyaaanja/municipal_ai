"""Security and behaviour tests for Phases 9-15."""
import io

from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase

from accounts.models import Notification
from chatbot.tools import REGISTRY, run_tool
from chatbot.tools.retrieval import search, tokenize
from chatbot.models import KnowledgeChunk
from civic.models import Proposal
from civic.services import create_proposal
from services.models import ServiceRequest
from services.services import create_service_request

User = get_user_model()

SERVICE = dict(
    service_type='BIRTH_CERT', ward_number=4, applicant_phone='9800000011',
    applicant_address='Dattatreya Square, Bhaktapur',
    details='I need a birth certificate for my daughter born last month.',
)
PROPOSAL = dict(
    category='INFRASTRUCTURE', title='Street lighting for Ward 5',
    ward_number=5,
    description='Ward 5 has no working street lights along the main lane, '
                'which makes the evening walk to the temple unsafe for elders.',
)


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()
        self.user = User.objects.create_user(
            email='applicant@example.com', password='pw-applicant-1')
        self.other = User.objects.create_user(
            email='other@example.com', password='pw-other-1')

    def request(self, user=None, files=None):
        req = self.rf.post('/chat/')
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req.user = user if user is not None else _Anon()
        if files is not None:
            req.FILES.setlist('photos', files)
        return req


class _Anon:
    is_authenticated = False
    is_staff = False
    pk = None
    role = None


class ServiceRequestToolTests(Base):
    def test_anonymous_cannot_draft(self):
        result = run_tool('draft_service_request', self.request(), **SERVICE)
        self.assertFalse(result.ok)
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_draft_creates_nothing(self):
        result = run_tool('draft_service_request', self.request(self.user), **SERVICE)
        self.assertTrue(result.ok)
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_confirm_creates_one_with_real_reference(self):
        req = self.request(self.user)
        token = run_tool('draft_service_request', req, **SERVICE).data['token']
        result = run_tool('confirm_service_request', req, token=token)
        self.assertTrue(result.ok)
        self.assertEqual(ServiceRequest.objects.count(), 1)
        ref = result.data['reference_number']
        self.assertTrue(ServiceRequest.objects.filter(reference_number=ref).exists())

    def test_token_is_single_use(self):
        req = self.request(self.user)
        token = run_tool('draft_service_request', req, **SERVICE).data['token']
        run_tool('confirm_service_request', req, token=token)
        again = run_tool('confirm_service_request', req, token=token)
        self.assertFalse(again.ok)
        self.assertEqual(ServiceRequest.objects.count(), 1)

    def test_another_user_cannot_confirm(self):
        token = run_tool('draft_service_request',
                         self.request(self.user), **SERVICE).data['token']
        result = run_tool('confirm_service_request',
                          self.request(self.other), token=token)
        self.assertFalse(result.ok)
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_invalid_service_type_refused(self):
        bad = dict(SERVICE, service_type='FREE_MONEY')
        self.assertFalse(run_tool('draft_service_request',
                                  self.request(self.user), **bad).ok)

    def test_service_layer_rejects_anonymous(self):
        with self.assertRaises(ValidationError):
            create_service_request(applicant=None, **SERVICE,
                                   applicant_name='X')
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_fee_is_never_model_supplied(self):
        req = self.request(self.user)
        token = run_tool('draft_service_request', req, **SERVICE).data['token']
        data = run_tool('confirm_service_request', req, token=token).data
        sr = ServiceRequest.objects.get()
        expected = str(sr.fee_amount) if sr.fee_amount is not None else None
        self.assertEqual(data['fee_amount'], expected)


class ProposalToolTests(Base):
    def test_anonymous_cannot_draft(self):
        self.assertFalse(run_tool('draft_proposal', self.request(), **PROPOSAL).ok)
        self.assertEqual(Proposal.objects.count(), 0)

    def test_confirm_creates_proposal_owned_by_caller(self):
        req = self.request(self.user)
        token = run_tool('draft_proposal', req, **PROPOSAL).data['token']
        result = run_tool('confirm_proposal', req, token=token)
        self.assertTrue(result.ok)
        self.assertEqual(Proposal.objects.get().submitted_by, self.user)

    def test_injected_author_argument_is_refused(self):
        """The tool signature is the allowlist: unknown arguments fail closed."""
        result = run_tool('draft_proposal', self.request(self.user),
                          submitted_by=self.other.pk, **PROPOSAL)
        self.assertFalse(result.ok)
        self.assertIsNone(result.data)
        self.assertEqual(Proposal.objects.count(), 0)

    def test_author_always_comes_from_the_session(self):
        req = self.request(self.user)
        token = run_tool('draft_proposal', req, **PROPOSAL).data['token']
        run_tool('confirm_proposal', req, token=token)
        self.assertEqual(Proposal.objects.get().submitted_by, self.user)

    def test_another_user_cannot_confirm(self):
        token = run_tool('draft_proposal',
                         self.request(self.user), **PROPOSAL).data['token']
        self.assertFalse(run_tool('confirm_proposal',
                                  self.request(self.other), token=token).ok)
        self.assertEqual(Proposal.objects.count(), 0)

    def test_short_description_refused(self):
        bad = dict(PROPOSAL, description='fix it')
        self.assertFalse(run_tool('draft_proposal',
                                  self.request(self.user), **bad).ok)

    def test_invalid_category_refused(self):
        bad = dict(PROPOSAL, category='ADMIN')
        self.assertFalse(run_tool('draft_proposal',
                                  self.request(self.user), **bad).ok)


class Phase11TrackingTests(Base):
    def test_created_records_become_visible_to_their_owner(self):
        """Phase 11: what Phase 9/10 create, the read tools surface."""
        create_service_request(applicant=self.user, applicant_name='A', **SERVICE)
        create_proposal(submitted_by=self.user, **PROPOSAL)

        mine = run_tool('get_my_service_requests', self.request(self.user))
        props = run_tool('get_my_proposals', self.request(self.user))
        self.assertEqual(len(mine.data), 1)
        self.assertEqual(len(props.data), 1)

        theirs = run_tool('get_my_service_requests', self.request(self.other))
        self.assertEqual(theirs.data, [])


class RetrievalTests(TestCase):
    def setUp(self):
        cache.clear()
        KnowledgeChunk.objects.create(
            source_type='service', title='Property Tax Payment',
            content='Property tax is paid at the municipality office. '
                    'Bring your ownership document and citizenship certificate.',
            is_active=True)
        KnowledgeChunk.objects.create(
            source_type='culture', title='Bisket Jatra',
            content='Bisket Jatra marks the Nepali new year with a chariot '
                    'procession through Bhaktapur.', is_active=True)

    def test_nepali_query_reaches_english_content(self):
        """The exact failure that made icontains unusable."""
        hits = search('कर कसरी तिर्ने?')
        self.assertTrue(hits)
        self.assertEqual(hits[0]['title'], 'Property Tax Payment')

    def test_english_query_still_works(self):
        hits = search('how do I pay property tax')
        self.assertEqual(hits[0]['title'], 'Property Tax Payment')

    def test_ranking_prefers_the_better_chariot_match(self):
        hits = search('chariot procession new year')
        self.assertEqual(hits[0]['title'], 'Bisket Jatra')

    def test_devanagari_tokenised(self):
        self.assertIn('कर', tokenize('कर कसरी तिर्ने?'))

    def test_nonsense_query_returns_nothing(self):
        self.assertEqual(search('zzzzqqqq'), [])

    def test_empty_query_returns_nothing(self):
        self.assertEqual(search(''), [])

    def test_tool_reports_not_found_rather_than_inventing(self):
        rf = RequestFactory()
        req = rf.post('/chat/')
        req.user = _Anon()
        result = run_tool('search_municipal_knowledge', req, query='zzzzqqqq')
        self.assertTrue(result.ok)
        self.assertFalse(result.data['found'])
        self.assertEqual(result.data['passages'], [])


class MapToolTests(Base):
    def test_map_returns_only_published_coordinates(self):
        from tourism.models import Attraction
        Attraction.objects.create(
            name='Nyatapola Temple', slug='nyatapola-map', description='Five storey temple.',
            latitude='27.6710000', longitude='85.4298000', is_active=True)
        Attraction.objects.create(
            name='Nyatapola Annex', slug='nyatapola-annex', description='No coordinates.',
            is_active=True)
        result = run_tool('find_on_map', self.request(), query='Nyatapola')
        self.assertTrue(result.ok)
        self.assertEqual(len(result.data), 1)
        self.assertEqual(result.data[0]['name'], 'Nyatapola Temple')


class NotificationWriteTests(Base):
    def test_marking_read_only_touches_own_notifications(self):
        Notification.objects.create(user=self.user, message='Yours')
        Notification.objects.create(user=self.other, message='Theirs')
        result = run_tool('mark_notifications_read', self.request(self.user))
        self.assertTrue(result.ok)
        self.assertEqual(result.data['marked_read'], 1)
        self.assertFalse(Notification.objects.get(user=self.other).is_read)

    def test_anonymous_refused(self):
        self.assertFalse(run_tool('mark_notifications_read', self.request()).ok)


class ContractTests(Base):
    def test_every_write_tool_is_authenticated_or_optional(self):
        for name, spec in REGISTRY.items():
            if name.startswith(('confirm_', 'draft_', 'mark_')):
                self.assertIn(spec.auth, ('required', 'optional'), name)
                self.assertFalse(spec.cacheable, name)
                self.assertTrue(spec.audit or name.startswith('mark_'), name)

    def test_every_tool_still_declares_a_limit(self):
        for spec in REGISTRY.values():
            self.assertTrue(spec.rate_user or spec.rate_ip, spec.name)

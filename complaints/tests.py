from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import Complaint

User = get_user_model()

CACHE_OVERRIDE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-cache',
    }
}

COMPLAINT_DATA = {
    'category': 'WATER',
    'title': 'No water in Taumadhi',
    'description': 'Water supply has been cut for 3 days.',
    'location': 'Taumadhi Tole',
    'name': 'Ram Shrestha',
    'phone': '',
    'email': '',
}


def make_complaint(**kwargs):
    data = dict(
        category='ROAD', title='Broken road', description='Big pothole',
        location='Dattatreya Square', submitter_name='Test User',
    )
    data.update(kwargs)
    return Complaint.objects.create(**data)


@override_settings(CACHES=CACHE_OVERRIDE)
class ComplaintSubmitTests(TestCase):

    def test_submit_complaint_anonymous(self):
        """Anonymous POST to /complaint/ with valid data → 302 redirect to success."""
        resp = self.client.post(reverse('complaints:complaint_submit'), COMPLAINT_DATA)
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('complaints:complaint_success'))

    def test_submit_sets_session(self):
        """After submit, session contains last_complaint_id."""
        self.client.post(reverse('complaints:complaint_submit'), COMPLAINT_DATA)
        self.assertIn('last_complaint_id', self.client.session)
        cid = self.client.session['last_complaint_id']
        self.assertTrue(cid.startswith('BK-'))

    def test_success_clears_session(self):
        """Visiting success page clears last_complaint_id from session."""
        self.client.post(reverse('complaints:complaint_submit'), COMPLAINT_DATA)
        self.client.get(reverse('complaints:complaint_success'))
        self.assertNotIn('last_complaint_id', self.client.session)

    def test_success_refresh_redirects(self):
        """Visiting success without session → redirect to submit (prevents double-show)."""
        resp = self.client.get(reverse('complaints:complaint_success'))
        self.assertRedirects(resp, reverse('complaints:complaint_submit'))

    def test_complaint_id_unique(self):
        """Two complaints get different BK-XXXXX IDs."""
        c1 = make_complaint(title='First')
        c2 = make_complaint(title='Second')
        self.assertNotEqual(c1.complaint_id, c2.complaint_id)


@override_settings(CACHES=CACHE_OVERRIDE)
class ComplaintTrackTests(TestCase):

    def setUp(self):
        self.complaint = make_complaint()

    def test_track_found(self):
        """POST to /complaint/track/ with valid ID → redirect to status page."""
        resp = self.client.post(
            reverse('complaints:complaint_track'),
            {'complaint_id': self.complaint.complaint_id}
        )
        self.assertRedirects(
            resp,
            reverse('complaints:complaint_status', args=[self.complaint.complaint_id])
        )

    def test_track_not_found(self):
        """POST with non-existent ID → re-renders track with error (200)."""
        resp = self.client.post(
            reverse('complaints:complaint_track'),
            {'complaint_id': 'BK-XXXXX'}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'No complaint found')

    def test_track_case_insensitive(self):
        """Lowercase ID still finds the complaint."""
        lower_id = self.complaint.complaint_id.lower()
        resp = self.client.post(
            reverse('complaints:complaint_track'),
            {'complaint_id': lower_id}
        )
        self.assertEqual(resp.status_code, 302)


@override_settings(CACHES=CACHE_OVERRIDE)
class ComplaintStatusTests(TestCase):

    def setUp(self):
        self.complaint = make_complaint(
            submitter_phone='9800000000',
            submitter_email='secret@test.com',
            admin_notes='Resolved after inspection.',
        )

    def test_status_hides_phone_email(self):
        """Public status page must not expose phone or email."""
        resp = self.client.get(
            reverse('complaints:complaint_status', args=[self.complaint.complaint_id])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, '9800000000')
        self.assertNotContains(resp, 'secret@test.com')

    def test_admin_notes_shown_always(self):
        """admin_notes appear whenever they are set, regardless of status (improvement plan 1.2)."""
        self.complaint.status = 'PENDING'
        self.complaint.save()
        resp = self.client.get(
            reverse('complaints:complaint_status', args=[self.complaint.complaint_id])
        )
        self.assertContains(resp, 'Resolved after inspection.')

    def test_admin_notes_shown_resolved(self):
        """admin_notes must appear when status is RESOLVED."""
        self.complaint.status = 'RESOLVED'
        self.complaint.save()
        resp = self.client.get(
            reverse('complaints:complaint_status', args=[self.complaint.complaint_id])
        )
        self.assertContains(resp, 'Resolved after inspection.')


@override_settings(CACHES=CACHE_OVERRIDE)
class AuthAndAccessTests(TestCase):

    def setUp(self):
        self.citizen = User.objects.create_user(
            email='citizen@test.com', password='Test1234!',
            username='citizen1', role='citizen',
        )
        self.staff_user = User.objects.create_user(
            email='staff@test.com', password='Test1234!',
            username='staff1', role='staff', is_staff=True,
        )

    def test_my_complaints_requires_login(self):
        """Anonymous user hitting /complaint/my/ → redirect to login."""
        resp = self.client.get(reverse('complaints:my_complaints'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp['Location'])

    def test_citizen_cannot_access_dashboard(self):
        """Citizen role → 403 on /dashboard/."""
        self.client.force_login(self.citizen)
        resp = self.client.get(reverse('dashboard:home'))
        self.assertEqual(resp.status_code, 403)

    def test_staff_can_access_dashboard(self):
        """Staff role → 200 on /dashboard/."""
        self.client.force_login(self.staff_user)
        resp = self.client.get(reverse('dashboard:home'))
        self.assertEqual(resp.status_code, 200)


@override_settings(CACHES=CACHE_OVERRIDE)
class RateLimitTest(TestCase):

    def test_rate_limit_blocks_4th_submission(self):
        """4th complaint submission from same IP within an hour → blocked (200 with error)."""
        for _ in range(3):
            self.client.post(reverse('complaints:complaint_submit'), COMPLAINT_DATA,
                             REMOTE_ADDR='10.0.0.1')
        resp = self.client.post(reverse('complaints:complaint_submit'), COMPLAINT_DATA,
                                REMOTE_ADDR='10.0.0.1')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Too many')

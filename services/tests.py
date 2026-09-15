import re
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from .models import ServiceRequest, ServiceRequestStatusHistory, PublicNotice

User = get_user_model()


def make_citizen(tag, ward=3):
    return User.objects.create_user(f'{tag}@test.com', password='testpass123',
                                    username=tag, ward_number=ward, role='citizen')


def make_mayor(tag):
    return User.objects.create_user(f'{tag}@test.com', password='testpass123',
                                    username=tag, role='mayor')


class ServiceRequestTests(TestCase):
    def setUp(self):
        self.citizen = make_citizen('sr_citizen')
        self.other = make_citizen('sr_other', ward=5)
        self.client = Client()

    def test_submit_requires_login(self):
        r = self.client.post('/services/apply/BIRTH_CERT/', {
            'applicant_name': 'Test', 'applicant_phone': '9800000000',
            'applicant_address': 'Bhaktapur', 'details': '',
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login/', r['Location'])

    def test_reference_format_SR_YYYYMM_XXXXXX(self):
        sr = ServiceRequest.objects.create(
            service_type='BIRTH_CERT',
            ward_number=3,
            applicant=self.citizen,
            applicant_name='Test',
            applicant_phone='9800000000',
            applicant_address='Bhaktapur',
            details='',
        )
        self.assertRegex(sr.reference_number, r'^SR-\d{6}-[A-Z0-9]{6}$')

    def test_citizen_cannot_view_other_request(self):
        sr = ServiceRequest.objects.create(
            service_type='BIRTH_CERT', ward_number=5,
            applicant=self.other, applicant_name='Other',
            applicant_phone='9800000000', applicant_address='BKT', details='',
        )
        self.client.login(email='sr_citizen@test.com', password='testpass123')
        r = self.client.get(f'/services/my/{sr.reference_number}/')
        self.assertEqual(r.status_code, 403)

    def test_status_history_created_on_update(self):
        sr = ServiceRequest.objects.create(
            service_type='BIRTH_CERT', ward_number=3,
            applicant=self.citizen, applicant_name='Test',
            applicant_phone='9800000000', applicant_address='BKT', details='',
        )
        ServiceRequestStatusHistory.objects.create(
            request=sr, old_status='', new_status='SUBMITTED',
            note='Initial submission',
        )
        self.assertEqual(sr.history.count(), 1)
        self.assertEqual(sr.history.first().new_status, 'SUBMITTED')


class PublicNoticeTests(TestCase):
    def setUp(self):
        self.mayor = make_mayor('notice_mayor')
        self.citizen = make_citizen('notice_citizen')
        self.notice = PublicNotice.objects.create(
            notice_type='NOTICE',
            title='Test Notice',
            body='This is a test notice.',
        )
        self.client = Client()

    def test_notice_list_public(self):
        r = self.client.get('/services/notices/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Test Notice')

    def test_notice_detail_public(self):
        r = self.client.get(f'/services/notices/{self.notice.pk}/')
        self.assertEqual(r.status_code, 200)

    def test_nav_links_to_public_notices_via_civic_dropdown(self):
        """Anonymous users can reach Public Notices from the navbar Civic dropdown."""
        r = self.client.get('/')
        self.assertContains(r, 'href="/services/notices/"')

    def test_anonymous_user_can_view_notices(self):
        """Public notice list is accessible without logging in."""
        self.client.logout()
        r = self.client.get('/services/notices/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Test Notice')

    def test_mayor_can_create(self):
        self.client.login(email='notice_mayor@test.com', password='testpass123')
        self.client.post('/services/mayor/notices/create/', {
            'notice_type': 'TENDER',
            'title': 'Road Construction Tender',
            'body': 'Details here...',
        })
        self.assertEqual(PublicNotice.objects.count(), 2)

    def test_citizen_cannot_create(self):
        self.client.login(email='notice_citizen@test.com', password='testpass123')
        r = self.client.post('/services/mayor/notices/create/', {
            'notice_type': 'TENDER',
            'title': 'Unauthorized Notice',
            'body': 'Should not work',
        })
        self.assertEqual(r.status_code, 403)

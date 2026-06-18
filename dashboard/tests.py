from django.test import TestCase
from accounts.models import User
from complaints.models import Complaint


def make_user(email, role='citizen', is_staff=False):
    return User.objects.create_user(
        email=email, username=email.split('@')[0],
        password='Pass1234!', first_name='T', last_name='U',
        role=role, is_staff=is_staff
    )


def make_complaint():
    return Complaint.objects.create(
        title='Road Damage', category='ROAD',
        description='Big pothole on main road.',
        location='Main Street, Ward 5',
        submitter_name='Test User',
        status='PENDING',
    )


class DashboardAccessTests(TestCase):
    def test_anonymous_redirected(self):
        r = self.client.get('/dashboard/')
        self.assertEqual(r.status_code, 302)

    def test_citizen_forbidden(self):
        make_user('citizen@test.com', role='citizen')
        self.client.login(username='citizen@test.com', password='Pass1234!')
        r = self.client.get('/dashboard/')
        self.assertEqual(r.status_code, 403)

    def test_staff_can_access(self):
        make_user('staff@test.com', role='staff', is_staff=True)
        self.client.login(username='staff@test.com', password='Pass1234!')
        r = self.client.get('/dashboard/')
        self.assertEqual(r.status_code, 200)

    def test_official_can_access(self):
        make_user('official@test.com', role='official')
        self.client.login(username='official@test.com', password='Pass1234!')
        r = self.client.get('/dashboard/')
        self.assertEqual(r.status_code, 200)

    def test_admin_can_access(self):
        make_user('admin@test.com', role='admin')
        self.client.login(username='admin@test.com', password='Pass1234!')
        r = self.client.get('/dashboard/')
        self.assertEqual(r.status_code, 200)


class DashboardComplaintListTests(TestCase):
    def setUp(self):
        self.staff = make_user('staff2@test.com', role='staff', is_staff=True)
        self.client.login(username='staff2@test.com', password='Pass1234!')
        self.complaint = make_complaint()

    def test_complaints_list_loads(self):
        r = self.client.get('/dashboard/complaints/')
        self.assertEqual(r.status_code, 200)

    def test_complaints_list_shows_complaint(self):
        r = self.client.get('/dashboard/complaints/')
        self.assertContains(r, 'Road Damage')

    def test_complaint_detail_loads(self):
        r = self.client.get(f'/dashboard/complaints/{self.complaint.complaint_id}/')
        self.assertEqual(r.status_code, 200)

    def test_status_update_by_staff(self):
        r = self.client.post(
            f'/dashboard/complaints/{self.complaint.complaint_id}/',
            {'status': 'IN_PROGRESS', 'admin_notes': 'Being reviewed.'}
        )
        self.assertIn(r.status_code, [200, 302])
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, 'IN_PROGRESS')


class ExportTests(TestCase):
    def setUp(self):
        self.staff = make_user('exp@test.com', role='official')
        self.client.login(username='exp@test.com', password='Pass1234!')
        make_complaint()

    def test_export_csv(self):
        r = self.client.get('/dashboard/export/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'text/csv')

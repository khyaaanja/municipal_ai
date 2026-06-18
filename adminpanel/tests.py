from django.test import TestCase
from accounts.models import User


def make_staff(email='admin@test.com'):
    return User.objects.create_user(
        email=email, username=email.split('@')[0],
        password='Pass1234!', first_name='A', last_name='D',
        role='admin', is_staff=True, is_superuser=True
    )


def make_citizen(email='cit@test.com'):
    return User.objects.create_user(
        email=email, username=email.split('@')[0],
        password='Pass1234!', first_name='C', last_name='I', role='citizen'
    )


class AdminPanelAccessTests(TestCase):
    def test_anonymous_redirected(self):
        r = self.client.get('/admin/dashboard/')
        self.assertEqual(r.status_code, 302)

    def test_citizen_forbidden(self):
        make_citizen()
        self.client.login(username='cit@test.com', password='Pass1234!')
        r = self.client.get('/admin/dashboard/')
        self.assertEqual(r.status_code, 403)

    def test_staff_can_access(self):
        make_staff()
        self.client.login(username='admin@test.com', password='Pass1234!')
        r = self.client.get('/admin/dashboard/')
        self.assertEqual(r.status_code, 200)


class CMSAttractionsTests(TestCase):
    def setUp(self):
        make_staff()
        self.client.login(username='admin@test.com', password='Pass1234!')

    def test_list_loads(self):
        r = self.client.get('/admin/cms/attractions/')
        self.assertEqual(r.status_code, 200)

    def test_add_form_loads(self):
        r = self.client.get('/admin/cms/attractions/add/')
        self.assertEqual(r.status_code, 200)

    def test_create_attraction(self):
        r = self.client.post('/admin/cms/attractions/add/', {
            'name': 'Test Temple', 'description': 'Ancient temple.',
            'is_active': 'on',
        })
        self.assertRedirects(r, '/admin/cms/attractions/', fetch_redirect_response=False)
        from tourism.models import Attraction
        self.assertTrue(Attraction.objects.filter(name='Test Temple').exists())


class CMSEventsTests(TestCase):
    def setUp(self):
        make_staff()
        self.client.login(username='admin@test.com', password='Pass1234!')

    def test_list_loads(self):
        r = self.client.get('/admin/cms/events/')
        self.assertEqual(r.status_code, 200)

    def test_create_event(self):
        r = self.client.post('/admin/cms/events/add/', {
            'name': 'New Festival', 'description': 'Big event.',
            'category': 'festival', 'venue': 'Durbar Square',
            'start_date': '2027-04-14', 'is_active': 'on', 'is_free': 'on',
        })
        self.assertRedirects(r, '/admin/cms/events/', fetch_redirect_response=False)
        from events.models import Event
        self.assertTrue(Event.objects.filter(name='New Festival').exists())


class CMSNewsTests(TestCase):
    def setUp(self):
        self.admin = make_staff()
        self.client.login(username='admin@test.com', password='Pass1234!')

    def test_list_loads(self):
        r = self.client.get('/admin/cms/news/')
        self.assertEqual(r.status_code, 200)

    def test_create_article(self):
        r = self.client.post('/admin/cms/news/add/', {
            'title': 'Mayor Announcement', 'summary': 'Important news.',
            'content': 'Full content here.', 'category': 'general',
            'is_active': 'on',
        })
        self.assertRedirects(r, '/admin/cms/news/', fetch_redirect_response=False)
        from news.models import NewsArticle
        self.assertTrue(NewsArticle.objects.filter(title='Mayor Announcement').exists())

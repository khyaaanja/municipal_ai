from django.test import TestCase
from accounts.models import User


class HomepageTests(TestCase):
    def test_homepage_loads(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)

    def test_homepage_contains_brand(self):
        r = self.client.get('/')
        self.assertContains(r, 'Bhaktapur')

    def test_search_get(self):
        r = self.client.get('/search/?q=temple')
        self.assertEqual(r.status_code, 200)

    def test_search_empty_query(self):
        r = self.client.get('/search/?q=')
        self.assertEqual(r.status_code, 200)

    def test_map_page_loads(self):
        r = self.client.get('/map/')
        self.assertEqual(r.status_code, 200)

    def test_orders_requires_login(self):
        r = self.client.get('/orders/')
        self.assertEqual(r.status_code, 302)

    def test_orders_logged_in(self):
        User.objects.create_user(
            email='ord@test.com', username='ord',
            password='Pass1234!', first_name='O', last_name='R'
        )
        self.client.login(username='ord@test.com', password='Pass1234!')
        r = self.client.get('/orders/')
        self.assertEqual(r.status_code, 200)

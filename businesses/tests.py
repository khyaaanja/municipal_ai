from django.test import TestCase
from businesses.models import Business


def make_business(name='Bhaktapur Crafts', **kw):
    defaults = dict(
        slug=name.lower().replace(' ', '-'),
        description='A local business.',
        category='retail',
        address='Durbar Square',
        is_active=True,
    )
    defaults.update(kw)
    return Business.objects.create(name=name, **defaults)


class BusinessListTests(TestCase):
    def test_list_loads(self):
        r = self.client.get('/businesses/')
        self.assertEqual(r.status_code, 200)

    def test_list_shows_businesses(self):
        make_business('Thangka Gallery')
        r = self.client.get('/businesses/')
        self.assertContains(r, 'Thangka Gallery')

    def test_inactive_hidden(self):
        make_business('Closed Shop', slug='closed-shop', is_active=False)
        r = self.client.get('/businesses/')
        self.assertNotContains(r, 'Closed Shop')


class BusinessDetailTests(TestCase):
    def setUp(self):
        self.b = make_business('Pottery House', slug='pottery-house')

    def test_detail_loads(self):
        r = self.client.get('/businesses/pottery-house/')
        self.assertEqual(r.status_code, 200)

    def test_detail_shows_name(self):
        r = self.client.get('/businesses/pottery-house/')
        self.assertContains(r, 'Pottery House')

    def test_404_on_missing(self):
        r = self.client.get('/businesses/no-such-place/')
        self.assertEqual(r.status_code, 404)

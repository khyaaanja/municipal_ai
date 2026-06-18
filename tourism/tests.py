from django.test import TestCase
from tourism.models import Attraction, AttractionCategory


def make_category(name='Temples', icon='🛕'):
    return AttractionCategory.objects.create(name=name, slug=name.lower(), icon=icon)


def make_attraction(name='Nyatapola', category=None, **kw):
    return Attraction.objects.create(
        name=name, slug=name.lower().replace(' ', '-'),
        description='Test description.', is_active=True,
        category=category, **kw
    )


class AttractionListTests(TestCase):
    def setUp(self):
        self.cat = make_category()
        self.a1 = make_attraction('Nyatapola Temple', self.cat)
        self.a2 = make_attraction('Pottery Square', self.cat)

    def test_list_loads(self):
        r = self.client.get('/attractions/')
        self.assertEqual(r.status_code, 200)

    def test_list_shows_attractions(self):
        r = self.client.get('/attractions/')
        self.assertContains(r, 'Nyatapola Temple')
        self.assertContains(r, 'Pottery Square')

    def test_category_filter(self):
        other_cat = make_category('Museums', '🏛️')
        make_attraction('Art Museum', other_cat)
        r = self.client.get('/attractions/?category=museums')
        self.assertContains(r, 'Art Museum')

    def test_search_filter(self):
        r = self.client.get('/attractions/?q=Nyatapola')
        self.assertContains(r, 'Nyatapola')

    def test_search_no_results(self):
        r = self.client.get('/attractions/?q=xyznonexistent')
        self.assertEqual(r.status_code, 200)


class AttractionDetailTests(TestCase):
    def setUp(self):
        self.cat = make_category()
        self.a = make_attraction('Changu Narayan', self.cat)

    def test_detail_loads(self):
        r = self.client.get(f'/attractions/{self.a.slug}/')
        self.assertEqual(r.status_code, 200)

    def test_detail_shows_name(self):
        r = self.client.get(f'/attractions/{self.a.slug}/')
        self.assertContains(r, 'Changu Narayan')

    def test_404_on_bad_slug(self):
        r = self.client.get('/attractions/does-not-exist/')
        self.assertEqual(r.status_code, 404)

"""Every page must render a real browser title.

The base template used to interpolate {{ page_title }} unconditionally, so
any view that did not set it produced "— Bhaktapur City Platform" — a title
starting with a dash, visible in the browser tab, in search results and in
anything that unfurls a shared link.
"""
from django.core.cache import cache
from django.test import TestCase


class PageTitleTests(TestCase):
    def setUp(self):
        # attractions_list caches its rendered response, so without this the
        # suite asserts against HTML rendered before the template changed.
        cache.clear()

    PUBLIC_ROUTES = [
        '/', '/attractions/', '/events/', '/businesses/', '/news/',
        '/complaint/', '/complaint/track/', '/services/notices/',
        '/announcements/', '/ward-projects/', '/login/', '/register/',
    ]

    def title_of(self, path):
        resp = self.client.get(path, follow=True)
        self.assertEqual(resp.status_code, 200, path)
        body = resp.content.decode()
        start = body.find('<title>')
        self.assertNotEqual(start, -1, f'{path} has no <title>')
        return body[start + 7:body.find('</title>', start)].strip()

    def test_no_page_starts_with_a_dash(self):
        for route in self.PUBLIC_ROUTES:
            title = self.title_of(route)
            self.assertFalse(title.startswith('—'),
                             f'{route} title starts with a dash: {title!r}')
            self.assertFalse(title.startswith('-'), f'{route}: {title!r}')

    def test_every_page_names_itself(self):
        """A title of only the site name identifies nothing."""
        for route in self.PUBLIC_ROUTES:
            title = self.title_of(route)
            self.assertTrue(len(title) > 0, route)
            self.assertNotEqual(title, 'Bhaktapur City Platform', route)

    def test_attractions_names_itself(self):
        self.assertTrue(self.title_of('/attractions/').startswith('Attractions'))


class ServiceWorkerTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_registered_exactly_once(self):
        """A second register() call re-requested the worker on every load."""
        body = self.client.get('/').content.decode()
        self.assertEqual(body.count('serviceWorker.register'), 1)

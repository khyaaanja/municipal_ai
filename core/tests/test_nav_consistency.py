"""Navigation must be the same everywhere, and must lock the page behind it.

The report page shipped its own nav and hid the shared one, so the logo
wrapped onto two lines and the hamburger, scan button and theme toggle were
all missing. Opening the hamburger also left the page behind it scrolling.
"""
from django.core.cache import cache
from django.test import TestCase


class SharedNavigationTests(TestCase):
    #Pages that previously diverged, plus a control.
    ROUTES = ['/', '/complaint/', '/attractions/', '/news/', '/services/notices/']

    def setUp(self):
        cache.clear()

    def body(self, path):
        resp = self.client.get(path, follow=True)
        self.assertEqual(resp.status_code, 200, path)
        return resp.content.decode()

    def test_every_page_uses_the_shared_nav(self):
        for route in self.ROUTES:
            self.assertIn('id="mainNav"', self.body(route), route)

    def test_report_page_has_no_private_nav(self):
        body = self.body('/complaint/')
        self.assertNotIn('rp-nav', body)

    def test_report_page_does_not_hide_the_shared_nav(self):
        """`.footer, .nav {display:none}` blanked the real navigation."""
        body = self.body('/complaint/')
        self.assertNotIn('.footer, .nav { display: none; }', body)
        self.assertNotIn('.mobile-bottom-nav { display: none !important; }', body)

    def test_report_page_keeps_the_mobile_controls(self):
        body = self.body('/complaint/')
        for marker in ['class="hamburger"', 'id="mobileMenu"', 'mobile-bottom-nav']:
            self.assertIn(marker, body, marker)


class MobileMenuScrollLockTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_menu_locks_and_unlocks_the_page(self):
        body = self.client.get('/').content.decode()
        self.assertIn('_lockScroll', body)
        self.assertIn('_unlockScroll', body)

    def test_offset_is_captured_before_the_menu_opens(self):
        """Reading scrollY after display:block records the shifted position."""
        body = self.client.get('/').content.decode()
        capture = body.index('_menuScrollY = window.scrollY')
        show = body.index("m.style.display = 'block'", capture - 400)
        self.assertLess(capture, show)

    def test_menu_closes_on_escape_and_on_link_click(self):
        body = self.client.get('/').content.decode()
        self.assertIn("'Escape'", body)
        self.assertIn('closeMobileMenu', body)

    def test_hamburger_reports_its_state(self):
        body = self.client.get('/').content.decode()
        self.assertIn('aria-expanded', body)
        self.assertIn('aria-controls="mobileMenu"', body)

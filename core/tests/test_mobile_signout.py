"""Signing out has to be reachable on a phone.

Sign Out was the sixteenth and last entry in the mobile menu, rendering
below the fold on a 667px screen. Combined with the menu's own scrolling
being broken, there was no way to sign out on a phone at all.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class MobileSignOutTests(TestCase):
    PASSWORD = 'QaTester!2026'

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email='signout@example.invalid', password=self.PASSWORD,
            first_name='Sita')
        self.user.is_email_verified = True
        self.user.save()
        self.client.force_login(self.user)

    def body(self):
        return self.client.get('/').content.decode()

    def test_sign_out_appears_before_the_navigation_links(self):
        """Above the links, so it needs no scrolling to reach."""
        body = self.body()
        menu = body[body.index('id="mobileMenu"'):]
        signout = menu.index('class="mobile-signout"')
        first_link = menu.index('Attractions')
        self.assertLess(signout, first_link)

    def test_exactly_one_sign_out_control_in_the_mobile_menu(self):
        body = self.body()
        menu = body[body.index('id="mobileMenu"'):body.index('</nav>')]
        self.assertEqual(menu.count('class="mobile-signout"'), 1)

    def test_menu_names_the_signed_in_user(self):
        self.assertIn('Signed in as', self.body())
        self.assertIn('Sita', self.body())

    def test_sign_out_actually_ends_the_session(self):
        resp = self.client.post(reverse('accounts:logout'), follow=True)
        self.assertEqual(resp.status_code, 200)
        after = self.client.get('/my/', follow=False)
        self.assertEqual(after.status_code, 302)
        self.assertIn('/login', after['Location'])

    def test_anonymous_visitor_sees_no_sign_out(self):
        self.client.logout()
        body = self.body()
        # The class is styled in the stylesheet regardless; what must be
        # absent is the control itself.
        self.assertNotIn('class="mobile-signout"', body)
        self.assertNotIn('Signed in as', body)
        self.assertIn('Sign In', body)

    def test_sign_out_is_a_post_not_a_link(self):
        """A GET-able logout is a CSRF footgun."""
        body = self.body()
        self.assertNotIn('<a href="/logout/"', body)
        self.assertIn('csrfmiddlewaretoken', body)

"""Login page rendering.

The unverified-email error used to carry an <a> tag inside the message
string. Django escapes template variables on output, correctly, so the
citizen was shown the raw markup instead of a link they could click.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class UnverifiedLoginTests(TestCase):
    PASSWORD = 'QaTester!2026'

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email='unverified@example.invalid', password=self.PASSWORD)
        self.user.is_email_verified = False
        self.user.role = 'citizen'
        self.user.save()

    def login(self):
        return self.client.post(reverse('accounts:login'), {
            'email': self.user.email, 'password': self.PASSWORD})

    def test_no_raw_markup_is_shown_to_the_user(self):
        body = self.login().content.decode()
        self.assertNotIn('&lt;a href', body)
        self.assertNotIn('&gt;Resend', body)

    def test_resend_link_is_a_real_anchor(self):
        body = self.login().content.decode()
        self.assertIn(reverse('accounts:resend_verification'), body)
        self.assertIn('Resend verification email', body)

    def test_message_still_explains_the_problem(self):
        self.assertIn('verify your email', self.login().content.decode())

    def test_verified_user_is_not_blocked(self):
        self.user.is_email_verified = True
        self.user.save()
        resp = self.login()
        self.assertEqual(resp.status_code, 302)

    def test_link_absent_for_other_errors(self):
        resp = self.client.post(reverse('accounts:login'), {
            'email': self.user.email, 'password': 'wrong-password'})
        self.assertNotIn('Resend verification email', resp.content.decode())

from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User


def make_user(email='test@test.com', role='citizen', **kw):
    return User.objects.create_user(
        email=email, username=email.split('@')[0],
        password='TestPass1!', first_name='Test', last_name='User',
        role=role, **kw
    )


class UserManagerTests(TestCase):
    def test_create_user_generates_username_when_omitted(self):
        first = User.objects.create_user(
            email='first@example.com',
            password='TestPass1!',
            first_name='First',
            last_name='User',
        )
        second = User.objects.create_user(
            email='second@example.com',
            password='TestPass1!',
            first_name='Second',
            last_name='User',
        )

        self.assertTrue(first.username)
        self.assertTrue(second.username)
        self.assertNotEqual(first.username, second.username)


class RegistrationTests(TestCase):
    def test_register_page_loads(self):
        r = self.client.get('/register/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'register')

    def test_register_valid_user(self):
        r = self.client.post('/register/', {
            'full_name': 'Ram Shrestha',
            'email': 'ram@test.com',
            'password': 'StrongPass1!',
            'confirm_password': 'StrongPass1!',
        })
        self.assertRedirects(r, '/my/?welcome=1', fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(email='ram@test.com').exists())

    def test_register_duplicate_email(self):
        make_user('dup@test.com')
        r = self.client.post('/register/', {
            'full_name': 'Dup User',
            'email': 'dup@test.com',
            'password': 'StrongPass1!',
            'confirm_password': 'StrongPass1!',
        })
        self.assertEqual(r.status_code, 200)

    def test_register_password_mismatch(self):
        r = self.client.post('/register/', {
            'full_name': 'Mismatch User',
            'email': 'mismatch@test.com',
            'password': 'StrongPass1!',
            'confirm_password': 'Different1!',
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(email='mismatch@test.com').exists())

    def test_register_weak_password(self):
        r = self.client.post('/register/', {
            'full_name': 'Weak User',
            'email': 'weak@test.com',
            'password': '123',
            'confirm_password': '123',
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(email='weak@test.com').exists())


class LoginTests(TestCase):
    def setUp(self):
        self.user = make_user('login@test.com')
        # tests expect a redirect on successful login; the app enforces email
        # verification for citizen role.
        self.user.is_email_verified = True
        self.user.save(update_fields=['is_email_verified'])


    def test_login_page_loads(self):
        r = self.client.get('/login/')
        self.assertEqual(r.status_code, 200)

    def test_login_valid_credentials(self):
        r = self.client.post('/login/', {'email': 'login@test.com', 'password': 'TestPass1!'})
        self.assertRedirects(r, '/my/', fetch_redirect_response=False)

    def test_login_wrong_password(self):
        r = self.client.post('/login/', {'email': 'login@test.com', 'password': 'wrong'})
        self.assertEqual(r.status_code, 200)

    def test_login_nonexistent_user(self):
        r = self.client.post('/login/', {'email': 'ghost@test.com', 'password': 'TestPass1!'})
        self.assertEqual(r.status_code, 200)

    def test_logout_redirects(self):
        self.client.login(username='login@test.com', password='TestPass1!')
        r = self.client.post('/logout/')
        self.assertIn(r.status_code, [200, 302])

    def test_next_param_respected(self):
        r = self.client.post('/login/?next=/attractions/', {
            'email': 'login@test.com', 'password': 'TestPass1!'
        })
        self.assertRedirects(r, '/attractions/', fetch_redirect_response=False)


class ProfileTests(TestCase):
    def setUp(self):
        self.user = make_user('profile@test.com')
        self.client.login(username='profile@test.com', password='TestPass1!')

    def test_profile_loads(self):
        r = self.client.get('/profile/')
        self.assertEqual(r.status_code, 200)

    def test_profile_requires_login(self):
        self.client.logout()
        r = self.client.get('/profile/')
        self.assertEqual(r.status_code, 302)


class TwoFactorSecurityTests(TestCase):
    def test_totp_rejects_external_next_url(self):
        import pyotp
        from accounts.models import encrypt_otp_secret
        user = make_user('2fa@test.com')
        user.otp_enabled = True
        secret = pyotp.random_base32()
        # Store encrypted, exactly as totp_setup does in production.
        user.otp_secret = encrypt_otp_secret(secret)
        user.save(update_fields=['otp_enabled', 'otp_secret'])
        self.client.force_login(user)

        response = self.client.post('/2fa/verify/', {
            'code': pyotp.TOTP(secret).now(),
            'next': 'https://attacker.example/phish',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')


class DefaultRoleTests(TestCase):
    def test_new_user_is_citizen(self):
        u = make_user('citizen@test.com')
        self.assertEqual(u.role, 'citizen')

    def test_staff_user_role(self):
        u = make_user('staff@test.com', role='staff', is_staff=True)
        self.assertEqual(u.role, 'staff')
        self.assertTrue(u.is_staff)

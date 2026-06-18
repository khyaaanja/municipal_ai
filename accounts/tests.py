from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User


def make_user(email='test@test.com', role='citizen', **kw):
    return User.objects.create_user(
        email=email, username=email.split('@')[0],
        password='TestPass1!', first_name='Test', last_name='User',
        role=role, **kw
    )


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
        self.assertRedirects(r, '/', fetch_redirect_response=False)
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

    def test_login_page_loads(self):
        r = self.client.get('/login/')
        self.assertEqual(r.status_code, 200)

    def test_login_valid_credentials(self):
        r = self.client.post('/login/', {'email': 'login@test.com', 'password': 'TestPass1!'})
        self.assertRedirects(r, '/', fetch_redirect_response=False)

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


class DefaultRoleTests(TestCase):
    def test_new_user_is_citizen(self):
        u = make_user('citizen@test.com')
        self.assertEqual(u.role, 'citizen')

    def test_staff_user_role(self):
        u = make_user('staff@test.com', role='staff', is_staff=True)
        self.assertEqual(u.role, 'staff')
        self.assertTrue(u.is_staff)

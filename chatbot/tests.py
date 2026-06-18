from django.test import TestCase
from accounts.models import User


def make_user(email='bot@test.com'):
    return User.objects.create_user(
        email=email, username=email.split('@')[0],
        password='Pass1234!', first_name='C', last_name='U'
    )


class ChatbotPageTests(TestCase):
    def test_chat_page_loads_anonymous(self):
        r = self.client.get('/chat/')
        self.assertEqual(r.status_code, 200)

    def test_chat_page_loads_logged_in(self):
        make_user()
        self.client.login(username='bot@test.com', password='Pass1234!')
        r = self.client.get('/chat/')
        self.assertEqual(r.status_code, 200)

    def test_history_requires_login(self):
        r = self.client.get('/chat/history/')
        self.assertEqual(r.status_code, 302)

    def test_history_loads_when_logged_in(self):
        make_user()
        self.client.login(username='bot@test.com', password='Pass1234!')
        r = self.client.get('/chat/history/')
        self.assertEqual(r.status_code, 200)

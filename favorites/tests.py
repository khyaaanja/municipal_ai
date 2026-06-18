from django.test import TestCase
from accounts.models import User
from tourism.models import Attraction, AttractionCategory
from favorites.models import Favorite


def make_user(email='fav@test.com'):
    return User.objects.create_user(
        email=email, username=email.split('@')[0],
        password='Pass1234!', first_name='F', last_name='U'
    )


def make_attraction():
    cat, _ = AttractionCategory.objects.get_or_create(name='Temples', slug='temples', icon='🛕')
    return Attraction.objects.create(
        name='Test Attraction', slug='test-attraction',
        description='Test.', is_active=True, category=cat
    )


class FavoritesAccessTests(TestCase):
    def test_list_requires_login(self):
        r = self.client.get('/favorites/')
        self.assertEqual(r.status_code, 302)

    def test_toggle_requires_login(self):
        r = self.client.post('/favorites/toggle/', {'item_type': 'attraction', 'item_id': 1})
        self.assertEqual(r.status_code, 302)

    def test_list_loads_when_logged_in(self):
        make_user()
        self.client.login(username='fav@test.com', password='Pass1234!')
        r = self.client.get('/favorites/')
        self.assertEqual(r.status_code, 200)


class FavoritesToggleTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.login(username='fav@test.com', password='Pass1234!')
        self.attraction = make_attraction()

    def test_add_favorite(self):
        import json
        r = self.client.post(
            '/favorites/toggle/',
            data=json.dumps({'content_type': 'attraction', 'object_id': self.attraction.pk}),
            content_type='application/json',
        )
        self.assertIn(r.status_code, [200, 302])
        self.assertTrue(
            Favorite.objects.filter(user=self.user, content_type='attraction',
                                    object_id=self.attraction.pk).exists()
        )

    def test_remove_favorite(self):
        import json
        fav = Favorite.objects.create(
            user=self.user, content_type='attraction', object_id=self.attraction.pk
        )
        r = self.client.post(
            '/favorites/toggle/',
            data=json.dumps({'favorite_id': fav.pk}),
            content_type='application/json',
        )
        self.assertIn(r.status_code, [200, 302])

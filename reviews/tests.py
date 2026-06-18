from django.test import TestCase
from accounts.models import User
from reviews.models import Review


def make_user(email='rev@test.com'):
    return User.objects.create_user(
        email=email, username=email.split('@')[0],
        password='Pass1234!', first_name='R', last_name='U'
    )


class ReviewSubmitTests(TestCase):
    def test_submit_requires_login(self):
        r = self.client.post('/reviews/submit/', {
            'content_type': 'attraction', 'object_id': 1,
            'rating': 5, 'comment': 'Great place!', 'next': '/'
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login/', r['Location'])

    def test_submit_creates_review(self):
        user = make_user()
        self.client.login(username='rev@test.com', password='Pass1234!')
        r = self.client.post('/reviews/submit/', {
            'content_type': 'attraction', 'object_id': 1,
            'rating': 4, 'comment': 'Very nice!', 'next': '/'
        })
        self.assertRedirects(r, '/', fetch_redirect_response=False)
        self.assertTrue(Review.objects.filter(user=user, content_type='attraction').exists())

    def test_submit_updates_existing_review(self):
        user = make_user()
        self.client.login(username='rev@test.com', password='Pass1234!')
        self.client.post('/reviews/submit/', {
            'content_type': 'attraction', 'object_id': 2,
            'rating': 3, 'comment': 'Okay.', 'next': '/'
        })
        self.client.post('/reviews/submit/', {
            'content_type': 'attraction', 'object_id': 2,
            'rating': 5, 'comment': 'Actually great!', 'next': '/'
        })
        rev = Review.objects.get(user=user, content_type='attraction', object_id=2)
        self.assertEqual(rev.rating, 5)
        self.assertEqual(rev.comment, 'Actually great!')

    def test_submit_without_comment_skipped(self):
        make_user()
        self.client.login(username='rev@test.com', password='Pass1234!')
        self.client.post('/reviews/submit/', {
            'content_type': 'attraction', 'object_id': 3,
            'rating': 5, 'comment': '', 'next': '/'
        })
        self.assertFalse(Review.objects.filter(content_type='attraction', object_id=3).exists())

    def test_rating_clamped_to_1_5(self):
        user = make_user()
        self.client.login(username='rev@test.com', password='Pass1234!')
        self.client.post('/reviews/submit/', {
            'content_type': 'attraction', 'object_id': 4,
            'rating': 99, 'comment': 'Overrated!', 'next': '/'
        })
        rev = Review.objects.get(user=user, object_id=4)
        self.assertEqual(rev.rating, 5)

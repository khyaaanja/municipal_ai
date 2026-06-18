from django.test import TestCase
from news.models import NewsArticle
from accounts.models import User


def make_author():
    return User.objects.create_user(
        email='author@test.com', username='author',
        password='Pass1234!', first_name='A', last_name='B'
    )


def make_article(title='Bhaktapur News', author=None, **kw):
    defaults = dict(
        slug=title.lower().replace(' ', '-'),
        summary='A summary.',
        content='Full content here.',
        category='general',
        is_active=True,
    )
    defaults.update(kw)
    return NewsArticle.objects.create(title=title, author=author, **defaults)


class NewsListTests(TestCase):
    def setUp(self):
        self.author = make_author()

    def test_list_loads(self):
        r = self.client.get('/news/')
        self.assertEqual(r.status_code, 200)

    def test_list_shows_articles(self):
        make_article('Festival Update', author=self.author)
        r = self.client.get('/news/')
        self.assertContains(r, 'Festival Update')

    def test_inactive_article_hidden(self):
        make_article('Draft Post', slug='draft-post', author=self.author, is_active=False)
        r = self.client.get('/news/')
        self.assertNotContains(r, 'Draft Post')


class NewsDetailTests(TestCase):
    def setUp(self):
        self.author = make_author()
        self.article = make_article('Mayor Speech', slug='mayor-speech', author=self.author)

    def test_detail_loads(self):
        r = self.client.get('/news/mayor-speech/')
        self.assertEqual(r.status_code, 200)

    def test_detail_shows_title(self):
        r = self.client.get('/news/mayor-speech/')
        self.assertContains(r, 'Mayor Speech')

    def test_404_on_missing(self):
        r = self.client.get('/news/no-such-article/')
        self.assertEqual(r.status_code, 404)

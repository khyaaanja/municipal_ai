from django.test import TestCase, RequestFactory
from django.http import HttpResponse
from core.middleware import RateLimitMiddleware


class RateLimitMiddlewareTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.mw = RateLimitMiddleware(lambda r: HttpResponse("ok"))

    def test_allows_normal_request(self):
        request = self.factory.get("/")
        response = self.mw(request)
        self.assertEqual(response.status_code, 200)

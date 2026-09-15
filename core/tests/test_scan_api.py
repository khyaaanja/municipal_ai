from django.test import TestCase, Client
import json
import base64


class ScanAPITest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_scan_no_image(self):
        response = self.client.post(
            "/api/scan/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_scan_invalid_json(self):
        response = self.client.post(
            "/api/scan/",
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_scan_image_too_small(self):
        data = {"image": base64.b64encode(b"tiny").decode()}
        response = self.client.post(
            "/api/scan/",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

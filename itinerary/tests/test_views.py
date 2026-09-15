from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from itinerary.models import Itinerary
import json

User = get_user_model()


class ItineraryViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123", role="citizen"
        )
        self.itinerary = Itinerary.objects.create(
            user=self.user,
            title="3-Day Trip",
            days=3,
            generated_plan=[{"day": 1, "title": "Day 1", "stops": []}],
        )

    def test_list_requires_login(self):
        response = self.client.get(reverse("itinerary:list"))
        self.assertEqual(response.status_code, 302)

    def test_list_shows_user_itineraries(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("itinerary:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "3-Day Trip")

    def test_detail_requires_login(self):
        response = self.client.get(reverse("itinerary:detail", args=[self.itinerary.pk]))
        self.assertEqual(response.status_code, 302)

    def test_detail_shows_itinerary(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("itinerary:detail", args=[self.itinerary.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Day 1")

    def test_generate_default_fallback(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("itinerary:generate"),
            data=json.dumps({"days": 2, "group_type": "solo", "interests": ["food"]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertFalse(data["ai_generated"])
        self.assertIn("itinerary_id", data)
        itin = Itinerary.objects.get(pk=data["itinerary_id"])
        self.assertEqual(itin.days, 2)

    def test_generate_invalid_json(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("itinerary:generate"),
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_generate_get_method_not_allowed(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("itinerary:generate"))
        self.assertEqual(response.status_code, 405)

    def test_delete_requires_login(self):
        response = self.client.post(reverse("itinerary:delete", args=[self.itinerary.pk]))
        self.assertEqual(response.status_code, 302)

    def test_delete_removes_itinerary(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("itinerary:delete", args=[self.itinerary.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(Itinerary.objects.count(), 0)

    def test_generate_clamps_days(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("itinerary:generate"),
            data=json.dumps({"days": 999, "group_type": "solo", "interests": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        itin = Itinerary.objects.get(pk=response.json()["itinerary_id"])
        self.assertEqual(itin.days, 14)

    def test_other_user_cannot_access_itinerary(self):
        other = User.objects.create_user(email="other@test.com", password="pass1234")
        self.client.force_login(other)
        response = self.client.get(reverse("itinerary:detail", args=[self.itinerary.pk]))
        self.assertEqual(response.status_code, 404)

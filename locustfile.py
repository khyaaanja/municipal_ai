"""
Load test for Bhaktapur Municipal AI Platform.
Simulates realistic user journeys — not just hammering one endpoint.

Run (headless, 200 users, 60s):
  locust --headless -u 200 -r 20 --run-time 60s --host http://127.0.0.1:8000

Run (UI mode):
  locust --host http://127.0.0.1:8000
"""
import json
import random
from locust import HttpUser, task, between, TaskSet


CHAT_MESSAGES = [
    "Tell me about Nyatapola Temple",
    "What is the entry fee for Bhaktapur Durbar Square?",
    "Best Newari restaurants near Taumadhi Square",
    "How do I get to Bhaktapur from Kathmandu?",
    "What are the opening hours of Changu Narayan?",
    "Plan a 2-day itinerary for Bhaktapur",
    "Emergency contact numbers",
    "What festivals are happening this month?",
    "Budget hotels in Bhaktapur",
    "Where can I buy Thangka paintings?",
    "Is Pottery Square free to visit?",
    "भक्तपुरको प्रवेश शुल्क कति हो?",
    "न्यातापोला मन्दिर कहाँ छ?",
    "What is Bisket Jatra?",
]

COMPLAINT_TITLES = [
    "Broken streetlight on Taumadhi Road",
    "Garbage not collected for 3 days",
    "Pothole near Pottery Square",
    "Water pipe leaking on Main Street",
]


class TouristUser(HttpUser):
    """
    Simulates a tourist browsing the site:
    reads homepage, checks attractions, uses AI chat.
    High frequency — 60% of traffic.
    """
    weight = 6
    wait_time = between(1, 4)

    def on_start(self):
        self.client.get("/")  # warm session / get CSRF

    def _csrf(self):
        return self.client.cookies.get("csrftoken", "")

    @task(5)
    def homepage(self):
        self.client.get("/", name="Homepage")

    @task(4)
    def ask_ai(self):
        msg = random.choice(CHAT_MESSAGES)
        self.client.post(
            "/api/chat/",
            json={"message": msg, "conversation_id": None},
            headers={"X-CSRFToken": self._csrf()},
            name="POST /api/chat/",
        )

    @task(3)
    def attractions_page(self):
        self.client.get("/attractions/", name="Attractions list")

    @task(2)
    def events_page(self):
        self.client.get("/events/", name="Events list")

    @task(2)
    def tourist_pass(self):
        self.client.get("/tourist-pass/", name="Tourist pass")

    @task(1)
    def marketplace(self):
        self.client.get("/marketplace/", name="Marketplace")

    @task(1)
    def chat_page(self):
        self.client.get("/chat/", name="Chat page")


class CitizenUser(HttpUser):
    """
    Simulates a Bhaktapur citizen: files complaints, checks news, uses services.
    Medium frequency — 30% of traffic.
    """
    weight = 3
    wait_time = between(2, 6)

    def on_start(self):
        self.client.get("/")

    def _csrf(self):
        return self.client.cookies.get("csrftoken", "")

    @task(4)
    def homepage(self):
        self.client.get("/", name="Homepage")

    @task(3)
    def complaint_page(self):
        self.client.get("/complaint/", name="Complaint form")

    @task(2)
    def ask_civic_ai(self):
        msg = random.choice([
            "How do I file a complaint about garbage collection?",
            "What services does the municipality offer?",
            "Water supply schedule for Bhaktapur",
            "How to get birth certificate from municipality?",
        ])
        self.client.post(
            "/api/chat/",
            json={"message": msg, "conversation_id": None},
            headers={"X-CSRFToken": self._csrf()},
            name="POST /api/chat/ (civic)",
        )

    @task(2)
    def news_page(self):
        self.client.get("/news/", name="News page")

    @task(1)
    def track_complaint(self):
        self.client.get(
            f"/complaint/track/?id=BKT-{random.randint(1000,9999)}",
            name="Track complaint",
        )


class BotCrawlerUser(HttpUser):
    """
    Simulates search engine crawlers / scrapers — lightweight GET requests.
    Low frequency — 10% of traffic.
    """
    weight = 1
    wait_time = between(0.5, 2)

    @task(3)
    def homepage(self):
        self.client.get("/", name="Homepage (bot)")

    @task(2)
    def sitemap(self):
        self.client.get("/sitemap.xml", name="Sitemap")

    @task(1)
    def robots(self):
        self.client.get("/robots.txt", name="robots.txt")

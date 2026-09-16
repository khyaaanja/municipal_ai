"""
Seeds the chatbot KnowledgeBase with real content pulled from Wikipedia.
Run:  python manage.py seed_knowledge
"""
import time
import requests
from django.core.management.base import BaseCommand
from core import contacts

WIKI_REST = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
HEADERS   = {"User-Agent": "BhaktapurMunicipalAI/1.0 (contact@bhaktapur.gov.np)"}

KNOWLEDGE_ENTRIES = [
    # (category, title, wiki_page, static_fallback, priority)
    ("general", "About Bhaktapur", "Bhaktapur",
     "Bhaktapur (also Bhadgaon or Khwopa) is an ancient Newar city in Bagmati Province, Nepal, "
     "founded in the 12th century and capital of the Malla kingdom. UNESCO World Heritage Site since 1979. "
     "Population ~83,000. Famous for pottery, woodcarving, Juju Dhau yoghurt, and festivals.",
     10),

    ("culture", "Bisket Jatra Festival", "Bisket_Jatra",
     "Bisket Jatra is Bhaktapur's most famous festival marking the Nepali New Year (mid-April). "
     "A massive chariot is pulled through the streets; the festival lasts 9 days with folk dances and rituals.",
     9),

    ("culture", "Newari Cuisine Guide", "Newari_cuisine",
     "Must-try Newari foods: Juju Dhau (King Yoghurt, NPR 80–120), Bara (lentil pancakes, NPR 30–50), "
     "Samay Baji (ritual platter), Choila (spiced meat), Yomari (sweet dumpling, seasonal). "
     "Best restaurants near Durbar Square and Taumadhi Square.",
     8),

    ("heritage", "Nyatapola Temple", "Nyatapola_Temple",
     "Nyatapola Temple in Taumadhi Square is Nepal's tallest pagoda (30 m), built in 1702 by King Bhupatindra Malla. "
     "The five storeys represent five elements of nature. Open 6 AM–8 PM, free entry.",
     9),

    ("heritage", "Changu Narayan Temple", "Changu_Narayan",
     "Changu Narayan is Nepal's oldest Vishnu temple (325 AD), on a hilltop with valley views. "
     "Features intricate stone and metal carvings. Entry NPR 300. Open 6 AM–7 PM.",
     8),

    ("heritage", "Bhaktapur Durbar Square", "Bhaktapur_Durbar_Square",
     "Bhaktapur Durbar Square is a UNESCO World Heritage Site featuring palaces, temples, and courtyards "
     "from the Malla kingdom era. Entry fee NPR 1500 (includes all squares). Open 7 AM–7 PM.",
     10),

    ("transport", "Getting to Bhaktapur", "Bhaktapur",
     "Bhaktapur is 16 km east of Kathmandu. Take Bus No.1 or microbus from Koteshwor/Kalanki (NPR 20–30). "
     "Electric tempos within the city (NPR 15). Taxis available — negotiate first. Walk the old city. "
     "Rickshaws near Durbar Square. No private cars allowed inside the heritage zone.",
     9),

    ("emergency", "Emergency Contacts Bhaktapur", None,
     "Police (Nepal): 100 | Fire: 101 | Ambulance: 102 | "
     "Tourist Police Bhaktapur: +977-1-4247041 | "
     "Bhaktapur Municipality: " + contacts.PHONES + " | "
     "Bhaktapur Hospital: +977-1-6610798 | "
     "Embassy (US): +977-1-4234000",
     10),

    ("rules", "Visitor Rules & Entry Fees", None,
     "Entry fee: NPR 1500 for foreigners (covers all squares). SAARC nationals: NPR 500. "
     "Dress code: cover shoulders and knees at temples. Remove shoes before entering shrines. "
     "Photography allowed — respect privacy and rituals. No alcohol near temples. "
     "Littering is fined. Guides available at Durbar Square gate (NPR 500–1000/half-day).",
     9),

    ("culture", "Best Time to Visit", None,
     "Best: Oct–Nov (post-monsoon, Dashain festival, clear Himalayan views) and Mar–Apr (Bisket Jatra, spring). "
     "Avoid: Jun–Aug (monsoon — muddy paths, humid). Winter Dec–Jan is cold but dry and uncrowded. "
     "Mornings (7–9 AM) are best for photography and avoiding tour groups.",
     7),

    ("services", "Shopping & Handicrafts", None,
     "Bhaktapur specialities: Thangka paintings (NPR 1500–50,000+), pottery (NPR 80–2000), "
     "woodcarvings (NPR 500–20,000), bronze statues, Dhaka fabric, singing bowls. "
     "Best shopping: Pottery Square (fixed prices), Tachapal Tole antique shops, "
     "Durbar Square area (negotiate 20–30% below asking). Avoid touts — shop directly from artisans.",
     7),

    ("heritage", "Pottery Square (Kumale Tol)", "Bhaktapur",
     "Pottery Square is a living outdoor workshop where Prajapati (potter) families hand-throw clay pots "
     "using a traditional foot-kicked wheel. Watch artisans at work, buy pots directly. "
     "Free to visit. Located south-east of Durbar Square. Best visited in the morning.",
     8),

    ("services", "Accommodation in Bhaktapur", None,
     "Budget: Guesthouses near Durbar Square (NPR 500–1500/night). "
     "Mid-range: Heritage hotels in restored Newari buildings (NPR 1500–4000). "
     "Recommended: Bhadgaon Guest House (+977-1-6612120), Shiva Guest House, Hotel Heritage. "
     "Book ahead during festival season (Bisket Jatra, Dashain). Most hotels include breakfast.",
     6),

    ("culture", "Thangka Painting Tradition", "Thangka",
     "Thangka are Buddhist scroll paintings on cotton or silk, depicting deities, mandalas, and narrative scenes. "
     "Bhaktapur is a major centre of authentic Thangka production. "
     "Workshops offer 1–5 day courses (NPR 2000–5000). Buy only certified authentic pieces with artist signatures.",
     7),
]


class Command(BaseCommand):
    help = "Seed chatbot KnowledgeBase with real Wikipedia-sourced Bhaktapur content"

    def add_arguments(self, parser):
        parser.add_argument("--no-wiki", action="store_true",
                            help="Use static fallback text only, skip Wikipedia API")

    def handle(self, *args, **options):
        from chatbot.models import KnowledgeBase

        self.stdout.write(self.style.MIGRATE_HEADING("=== Seeding Chatbot Knowledge Base ==="))
        created_count  = 0
        updated_count  = 0

        for category, title, wiki_page, fallback, priority in KNOWLEDGE_ENTRIES:
            self.stdout.write(f"  • {title}")

            content = fallback  # default

            if wiki_page and not options["no_wiki"]:
                content = self._wiki_extract(wiki_page) or fallback
                time.sleep(0.4)

            obj, created = KnowledgeBase.objects.update_or_create(
                title=title,
                defaults={
                    "category": category,
                    "content":  content,
                    "priority": priority,
                    "is_active": True,
                }
            )
            if created:
                created_count += 1
                self.stdout.write(f"    Created ✓")
            else:
                updated_count += 1
                self.stdout.write(f"    Updated ✓")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone! {created_count} created, {updated_count} updated."
        ))

    def _wiki_extract(self, page_title: str) -> str:
        try:
            r = requests.get(
                WIKI_REST.format(page_title),
                headers=HEADERS, timeout=10
            )
            r.raise_for_status()
            extract = r.json().get("extract", "")
            # First 3 sentences only
            sentences = extract.split(". ")
            trimmed   = ". ".join(sentences[:3]).strip()
            if trimmed and not trimmed.endswith("."):
                trimmed += "."
            return trimmed
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    Wikipedia error: {e}"))
            return ""

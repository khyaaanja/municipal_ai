from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
import datetime


class Command(BaseCommand):
    help = 'Seed Bhaktapur municipal data'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding data...')
        self._roles()
        self._admin()
        self._categories()
        self._attractions()
        self._businesses()
        self._events()
        self._products()
        self._knowledge()
        self._news()
        self.stdout.write(self.style.SUCCESS('Done! Admin: admin@bhaktapur.gov.np / Admin@1234'))

    def _roles(self):
        from accounts.models import Role
        for r in ['guest', 'tourist', 'resident', 'vendor', 'staff', 'super_admin']:
            Role.objects.get_or_create(name=r)

    def _admin(self):
        from accounts.models import User, Role, Profile
        role = Role.objects.get(name='super_admin')
        if not User.objects.filter(email='admin@bhaktapur.gov.np').exists():
            u = User.objects.create_superuser(
                email='admin@bhaktapur.gov.np',
                password='Admin@1234',
                first_name='Admin',
                last_name='Bhaktapur',
                role=role,
            )
            Profile.objects.get_or_create(user=u)

    def _categories(self):
        from tourism.models import AttractionCategory
        cats = [
            ('Heritage Sites', 'heritage-sites', '🏛️'),
            ('Temples', 'temples', '⛩️'),
            ('Museums', 'museums', '🏛️'),
            ('Parks & Gardens', 'parks-gardens', '🌳'),
            ('Squares & Plazas', 'squares-plazas', '🏙️'),
        ]
        for name, slug, icon in cats:
            AttractionCategory.objects.get_or_create(
                slug=slug, defaults={'name': name, 'icon': icon}
            )

    def _attractions(self):
        from tourism.models import Attraction, AttractionCategory
        heritage = AttractionCategory.objects.get(slug='heritage-sites')
        temples = AttractionCategory.objects.get(slug='temples')
        squares = AttractionCategory.objects.get(slug='squares-plazas')
        museums = AttractionCategory.objects.get(slug='museums')

        data = [
            {
                'name': 'Bhaktapur Durbar Square',
                'slug': 'bhaktapur-durbar-square',
                'description': 'A UNESCO World Heritage Site featuring magnificent palaces, temples, and courtyards from the medieval Malla kingdom era. The square is the political, religious and social center of ancient Bhaktapur.',
                'category': squares,
                'address': 'Durbar Square, Bhaktapur 44800',
                'latitude': 27.6720, 'longitude': 85.4271,
                'opening_hours': '7:00 AM - 7:00 PM',
                'entry_fee': 1500, 'is_free': False,
                'is_featured': True,
            },
            {
                'name': 'Nyatapola Temple',
                'slug': 'nyatapola-temple',
                'description': 'The tallest pagoda-style temple in Nepal at 30 meters, built in 1702 AD by King Bhupatindra Malla. The five-storied temple represents the five elements of nature.',
                'category': temples,
                'address': 'Taumadhi Square, Bhaktapur',
                'latitude': 27.6717, 'longitude': 85.4284,
                'opening_hours': '6:00 AM - 8:00 PM',
                'is_free': True, 'entry_fee': None,
                'is_featured': True,
            },
            {
                'name': 'Pottery Square (Kumale Tol)',
                'slug': 'pottery-square',
                'description': 'Experience the living tradition of Newari pottery-making at this outdoor workshop where local artisans hand-throw clay pots using ancient techniques passed down for generations.',
                'category': heritage,
                'address': 'Pottery Square, Bhaktapur',
                'latitude': 27.6698, 'longitude': 85.4255,
                'opening_hours': '8:00 AM - 6:00 PM',
                'is_free': True, 'entry_fee': None,
                'is_featured': True,
            },
            {
                'name': 'National Art Museum',
                'slug': 'national-art-museum-bhaktapur',
                'description': 'Housed in the former palace of King Bhupatindra Malla, this museum features a rich collection of Thangka paintings, woodcarvings, metal crafts, and medieval Newari art.',
                'category': museums,
                'address': 'Durbar Square, Bhaktapur',
                'latitude': 27.6724, 'longitude': 85.4269,
                'opening_hours': '10:00 AM - 4:30 PM (Closed Tue)',
                'entry_fee': 200, 'is_free': False,
                'is_featured': True,
            },
            {
                'name': 'Changu Narayan Temple',
                'slug': 'changu-narayan-temple',
                'description': "Nepal's oldest Vishnu temple dating to 325 AD, perched atop a hillock with breathtaking views. Features intricate stone, metal and wood carvings of Hindu mythology.",
                'category': temples,
                'address': 'Changu, Bhaktapur District',
                'latitude': 27.7131, 'longitude': 85.4487,
                'opening_hours': '7:00 AM - 7:00 PM',
                'entry_fee': 300, 'is_free': False,
                'is_featured': True,
            },
            {
                'name': 'Taumadhi Square',
                'slug': 'taumadhi-square',
                'description': 'The second largest square in Bhaktapur, home to the iconic Nyatapola and Bhairavnath Temples. A vibrant hub of cultural activity and festivals.',
                'category': squares,
                'address': 'Taumadhi, Bhaktapur',
                'latitude': 27.6718, 'longitude': 85.4285,
                'opening_hours': 'Open 24 hours',
                'is_free': True, 'entry_fee': None,
                'is_featured': False,
            },
        ]
        for d in data:
            Attraction.objects.get_or_create(slug=d['slug'], defaults=d)

    def _businesses(self):
        from businesses.models import Business
        data = [
            {
                'name': 'Peacock Restaurant',
                'slug': 'peacock-restaurant',
                'description': 'Authentic Newari cuisine with panoramic views of Bhaktapur Durbar Square. Famous for Juju Dhau (King of Yoghurt) and Newari set meals.',
                'category': 'restaurant',
                'address': 'Durbar Square Area, Bhaktapur',
                'latitude': 27.6722, 'longitude': 85.4275,
                'phone': '+977-1-6610999',
                'opening_hours': '8:00 AM - 9:00 PM',
                'is_featured': True,
            },
            {
                'name': 'Bhadgaon Guest House',
                'slug': 'bhadgaon-guest-house',
                'description': 'Charming heritage guesthouse steps from Durbar Square. Traditional Newari architecture with modern amenities, rooftop terrace with mountain views.',
                'category': 'hotel',
                'address': 'Durbar Square, Bhaktapur 44800',
                'latitude': 27.6720, 'longitude': 85.4274,
                'phone': '+977-1-6612120',
                'opening_hours': 'Open 24 hours',
                'is_featured': True,
            },
            {
                'name': 'Café Nyatapola',
                'slug': 'cafe-nyatapola',
                'description': 'Cozy café inside a 500-year-old merchant house. Serves Nepali butter tea, filtered coffee, and traditional snacks with views of Taumadhi Square.',
                'category': 'cafe',
                'address': 'Taumadhi Square, Bhaktapur',
                'latitude': 27.6716, 'longitude': 85.4283,
                'phone': '+977-1-6614502',
                'opening_hours': '7:00 AM - 8:00 PM',
                'is_featured': True,
            },
            {
                'name': 'Heritage Handicraft Shop',
                'slug': 'heritage-handicraft-shop',
                'description': 'Family-run shop selling authentic Bhaktapur handicrafts: Thangka paintings, bronze sculptures, woodcarvings, pottery, and Dhaka fabric.',
                'category': 'shop',
                'address': 'Pottery Square, Bhaktapur',
                'latitude': 27.6699, 'longitude': 85.4253,
                'phone': '+977-9801234567',
                'opening_hours': '9:00 AM - 7:00 PM',
                'is_featured': False,
            },
            {
                'name': 'Marco Polo Restaurant',
                'slug': 'marco-polo-restaurant',
                'description': 'International and Nepali cuisine, popular with foreign tourists. Rooftop seating with views of the city. Good pizza and dal bhat.',
                'category': 'restaurant',
                'address': 'Sukuldhoka, Bhaktapur',
                'latitude': 27.6725, 'longitude': 85.4278,
                'phone': '+977-1-6613882',
                'opening_hours': '8:00 AM - 10:00 PM',
                'is_featured': True,
            },
        ]
        for d in data:
            Business.objects.get_or_create(slug=d['slug'], defaults=d)

    def _events(self):
        from events.models import Event
        now = timezone.now()
        data = [
            {
                'name': 'Bisket Jatra Festival',
                'slug': 'bisket-jatra',
                'description': "Bhaktapur's most famous festival marking the Nepali New Year. Features an enormous chariot pulled through the streets, folk dances, and ceremonial tug-of-war.",
                'category': 'festival',
                'venue': 'Bhaktapur City Center',
                'latitude': 27.6720, 'longitude': 85.4280,
                'start_date': now.replace(month=4, day=13, hour=6, minute=0),
                'is_free': True, 'organizer': 'Bhaktapur Municipality',
                'is_featured': True,
            },
            {
                'name': 'Thangka Painting Workshop',
                'slug': 'thangka-painting-workshop',
                'description': 'Learn traditional Thangka painting from master artists. 3-day immersive workshop covering sacred geometry, natural pigments, and Buddhist iconography.',
                'category': 'workshop',
                'venue': 'National Art Museum, Bhaktapur',
                'latitude': 27.6724, 'longitude': 85.4269,
                'start_date': now + datetime.timedelta(days=7),
                'entry_fee': 2500, 'is_free': False,
                'organizer': 'Bhaktapur Heritage Arts Center',
                'is_featured': True,
            },
            {
                'name': 'Newari Food Festival',
                'slug': 'newari-food-festival',
                'description': 'Three-day celebration of Newari gastronomy. Sample over 100 authentic dishes from local families, cooking competitions, and Juju Dhau tasting.',
                'category': 'food',
                'venue': 'Durbar Square, Bhaktapur',
                'latitude': 27.6720, 'longitude': 85.4271,
                'start_date': now + datetime.timedelta(days=14),
                'is_free': True,
                'organizer': 'Bhaktapur Tourism Board',
                'is_featured': True,
            },
            {
                'name': 'Heritage Photography Exhibition',
                'slug': 'heritage-photography-exhibition',
                'description': 'Annual exhibition showcasing the best photography of Bhaktapur and the Kathmandu Valley. Over 200 photos from local and international photographers.',
                'category': 'exhibition',
                'venue': 'National Art Museum, Bhaktapur',
                'latitude': 27.6724, 'longitude': 85.4269,
                'start_date': now + datetime.timedelta(days=21),
                'is_free': True,
                'organizer': 'Nepal Photography Society',
                'is_featured': False,
            },
        ]
        for d in data:
            Event.objects.get_or_create(slug=d['slug'], defaults=d)

    def _products(self):
        from marketplace.models import VendorProfile, Product, ProductCategory
        from accounts.models import User
        admin = User.objects.get(email='admin@bhaktapur.gov.np')
        vendor, _ = VendorProfile.objects.get_or_create(
            user=admin,
            defaults={
                'shop_name': 'Bhaktapur Heritage Store',
                'description': 'Authentic Bhaktapur handicrafts',
                'is_approved': True,
            }
        )
        cat, _ = ProductCategory.objects.get_or_create(
            slug='handicrafts', defaults={'name': 'Handicrafts', 'icon': '🎨'}
        )
        items = [
            ('Hand-painted Thangka', 'thangka-painting', 3500, 'Traditional Buddhist Thangka painting on cotton canvas, hand-painted with mineral pigments.'),
            ('Bhaktapur Pottery Bowl', 'pottery-bowl', 450, 'Hand-thrown pottery bowl made in the traditional style by Bhaktapur artisans.'),
            ('Woodcarved Window Panel', 'woodcarved-window', 2800, 'Intricate Newari woodcarving replica of the famous Peacock Window design.'),
            ('Juju Dhau (King Yoghurt)', 'juju-dhau', 120, 'Bhaktapur\'s famous thick, sweet yoghurt served in traditional clay pots. Made fresh daily.'),
            ('Bronze Ganesh Statue', 'bronze-ganesh', 1800, 'Hand-cast bronze Ganesh statue using the traditional Newari lost-wax casting technique.'),
            ('Dhaka Fabric Shawl', 'dhaka-shawl', 650, 'Hand-woven Dhaka fabric shawl with traditional geometric patterns. Ideal as a gift.'),
        ]
        for name, slug, price, desc in items:
            Product.objects.get_or_create(
                slug=slug,
                defaults={
                    'name': name, 'description': desc,
                    'price': price, 'vendor': vendor,
                    'category': cat, 'stock': 10, 'is_active': True,
                }
            )

    def _knowledge(self):
        from chatbot.models import KnowledgeBase
        entries = [
            ('emergency', 'Emergency Contacts',
             'Police: 100 | Fire Brigade: 101 | Ambulance: 102 | Tourist Police: +977-1-4247041 | Bhaktapur Municipality: +977-1-6610000 | Hospital: Bhaktapur Hospital +977-1-6610798'),
            ('transport', 'Getting Around Bhaktapur',
             'Bhaktapur is 16km from Kathmandu. Take Bus No.1 or microbus from Koteshwor/Kalanki (NPR 20-30). Electric tempos run within the city (NPR 15). Taxis available, negotiate price. The old city is best explored on foot. Rickshaws available near Durbar Square.'),
            ('rules', 'Visitor Guidelines',
             'Entry fee for foreigners: NPR 1500 (includes all squares). Dress modestly when visiting temples. Remove shoes before entering temples. Photography allowed but respect local customs. No alcohol near temples. Littering is prohibited and fined.'),
            ('general', 'About Bhaktapur',
             'Bhaktapur (also called Bhadgaon or Khwopa) is an ancient Newar city in the Bagmati Province, Nepal. Population ~83,000. Founded in 12th century, it was capital of the Malla kingdom. UNESCO World Heritage Site since 1979. Famous for pottery, woodcarving, Juju Dhau yoghurt, and festivals.'),
            ('culture', 'Best Time to Visit',
             'Best time: October-November (post-monsoon, clear skies, Dashain festival) and March-April (spring, Bisket Jatra). Avoid: June-August (monsoon, humid). Winter (Dec-Jan) is cold but clear. Mornings are best for photography. Arrive early to avoid tour groups.'),
            ('services', 'Local Food Guide',
             'Must try: Juju Dhau (King Yoghurt, NPR 80-120), Bara (lentil pancakes, NPR 30-50), Samay Baji (Newari platter, NPR 200-400), Choila (spiced meat), Yomari (sweet dumpling during festivals). Best restaurants near Durbar Square and Taumadhi Square. Avoid eating near temples during festivals.'),
        ]
        for category, title, content in entries:
            KnowledgeBase.objects.get_or_create(
                category=category,
                defaults={'title': title, 'content': content, 'is_active': True}
            )


    def _news(self):
        from news.models import NewsArticle
        from accounts.models import User
        admin = User.objects.get(email='admin@bhaktapur.gov.np')
        articles = [
            {
                'title': 'Bhaktapur Durbar Square Restoration Project Phase 2 Begins',
                'slug': 'durbar-square-restoration-phase-2',
                'summary': 'The municipality has commenced the second phase of post-earthquake restoration work at Bhaktapur Durbar Square.',
                'content': 'Bhaktapur Municipality has officially launched Phase 2 of the restoration project at the UNESCO World Heritage Site. The project, funded by international heritage organizations and the Government of Nepal, will focus on restoring the remaining earthquake-damaged structures including the 55-Window Palace facade and several smaller temples.',
                'category': 'development',
                'is_pinned': True,
                'author': admin,
            },
            {
                'title': 'Bisket Jatra 2081 Schedule Announced',
                'slug': 'bisket-jatra-2081-schedule',
                'summary': 'The official schedule for Bhaktapur\'s famous Bisket Jatra festival has been announced by the organizing committee.',
                'content': 'The Bisket Jatra organizing committee has released the complete schedule for this year\'s festival. The main chariot procession will begin at 6:00 AM on April 13 from Taumadhi Square. Thousands of devotees and tourists are expected to attend the week-long celebrations.',
                'category': 'event',
                'is_pinned': False,
                'author': admin,
            },
            {
                'title': 'New Visitor Center Opens Near Pottery Square',
                'slug': 'new-visitor-center-pottery-square',
                'summary': 'A modern visitor information center has been inaugurated near Pottery Square to better serve tourists exploring Bhaktapur.',
                'content': 'The new visitor center, built in traditional Newari architecture, provides tourist information, guided tour booking, luggage storage, and cultural exhibits. It is staffed by multilingual guides and is open daily from 8:00 AM to 6:00 PM.',
                'category': 'tourism',
                'is_pinned': False,
                'author': admin,
            },
        ]
        for a in articles:
            NewsArticle.objects.get_or_create(slug=a['slug'], defaults=a)

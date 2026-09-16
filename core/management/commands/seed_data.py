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
            ('Ponds & Water Bodies', 'ponds-water', '💧'),
            ('Sacred Sites', 'sacred-sites', '🙏'),
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
        parks = AttractionCategory.objects.get(slug='parks-gardens')
        ponds = AttractionCategory.objects.get(slug='ponds-water')
        sacred = AttractionCategory.objects.get(slug='sacred-sites')

        data = [
            # ── Squares & Plazas ──────────────────────────────────────────
            {
                'name': 'Bhaktapur Durbar Square',
                'slug': 'bhaktapur-durbar-square',
                'description': 'A UNESCO World Heritage Site featuring magnificent palaces, temples, and courtyards from the medieval Malla kingdom era. The square is the political, religious and social center of ancient Bhaktapur.',
                'category': squares,
                'address': 'Durbar Square, Bhaktapur 44800',
                'latitude': 27.6720, 'longitude': 85.4271,
                'opening_hours': '7:00 AM - 7:00 PM',
                'entry_fee': 1500, 'is_free': False, 'is_featured': True,
            },
            {
                'name': 'Taumadhi Square',
                'slug': 'taumadhi-square',
                'description': 'The second largest square in Bhaktapur, home to the iconic Nyatapola and Bhairavnath Temples. A vibrant hub of cultural activity and festivals.',
                'category': squares,
                'address': 'Taumadhi, Bhaktapur',
                'latitude': 27.6718, 'longitude': 85.4285,
                'opening_hours': 'Open 24 hours',
                'is_free': True, 'entry_fee': None, 'is_featured': True,
            },
            {
                'name': 'Dattatreya Square (Tachapal Tol)',
                'slug': 'dattatreya-square',
                'description': 'Bhaktapur\'s third major square and oldest, dating to the 15th century. Home to the Dattatreya Temple, Bhimsen Temple, and the famous Peacock Window at Pujari Math. A quieter, more authentic side of Bhaktapur.',
                'category': squares,
                'address': 'Tachapal Tol, Bhaktapur',
                'latitude': 27.6730, 'longitude': 85.4318,
                'opening_hours': 'Open 24 hours',
                'is_free': True, 'entry_fee': None, 'is_featured': True,
            },
            {
                'name': 'Golmadhi Square',
                'slug': 'golmadhi-square',
                'description': 'A smaller, less-visited square in the heart of Bhaktapur\'s old town. Features well-preserved Newari architecture, a sunken courtyard, and local street life away from the tourist crowds.',
                'category': squares,
                'address': 'Golmadhi, Bhaktapur',
                'latitude': 27.6710, 'longitude': 85.4300,
                'opening_hours': 'Open 24 hours',
                'is_free': True, 'entry_fee': None, 'is_featured': False,
            },
            # ── Temples ───────────────────────────────────────────────────
            {
                'name': 'Nyatapola Temple',
                'slug': 'nyatapola-temple',
                'description': 'The tallest pagoda-style temple in Nepal at 30 meters, built in 1702 AD by King Bhupatindra Malla. The five-storied temple represents the five elements of nature and is flanked by five pairs of guardian figures on its stairway.',
                'category': temples,
                'address': 'Taumadhi Square, Bhaktapur',
                'latitude': 27.6717, 'longitude': 85.4284,
                'opening_hours': '6:00 AM - 8:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': True,
            },
            {
                'name': 'Changu Narayan Temple',
                'slug': 'changu-narayan-temple',
                'description': "Nepal's oldest Vishnu temple dating to 325 AD, perched atop a forested hillock with breathtaking valley views. UNESCO World Heritage Site featuring some of the finest stone, metal and wood carvings of Hindu mythology in Nepal.",
                'category': temples,
                'address': 'Changu, Bhaktapur District',
                'latitude': 27.7131, 'longitude': 85.4487,
                'opening_hours': '7:00 AM - 7:00 PM',
                'entry_fee': 300, 'is_free': False, 'is_featured': True,
            },
            {
                'name': 'Bhairavnath Temple',
                'slug': 'bhairavnath-temple',
                'description': 'A three-storied pagoda temple dedicated to Bhairav, the terrifying manifestation of Shiva. The temple at Taumadhi Square is one of the most revered in Bhaktapur and central to the annual Bisket Jatra festival.',
                'category': temples,
                'address': 'Taumadhi Square, Bhaktapur',
                'latitude': 27.6716, 'longitude': 85.4283,
                'opening_hours': '6:00 AM - 9:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': True,
            },
            {
                'name': 'Siddhi Laxmi Temple',
                'slug': 'siddhi-laxmi-temple',
                'description': 'A unique stone temple at Bhaktapur Durbar Square dedicated to the goddess Siddhi Laxmi. Its steep stairway is flanked by a procession of stone guardians — men, women, horses, and mythological beasts.',
                'category': temples,
                'address': 'Durbar Square, Bhaktapur',
                'latitude': 27.6722, 'longitude': 85.4267,
                'opening_hours': '6:00 AM - 7:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': False,
            },
            {
                'name': 'Batsaladevi Temple',
                'slug': 'batsaladevi-temple',
                'description': 'An ornate 17th-century temple dedicated to the goddess Batsaladevi, located at Bhaktapur Durbar Square. Its huge bronze bell and the famous Taleju Bell are iconic landmarks of the square.',
                'category': temples,
                'address': 'Durbar Square, Bhaktapur',
                'latitude': 27.6721, 'longitude': 85.4270,
                'opening_hours': '6:00 AM - 7:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': False,
            },
            {
                'name': 'Wakupati Narayan Temple',
                'slug': 'wakupati-narayan-temple',
                'description': 'A beautifully proportioned three-tiered pagoda temple dedicated to Narayan (Vishnu), located in the eastern part of Bhaktapur\'s old town. Features exquisite woodcarving on the struts and torana.',
                'category': temples,
                'address': 'Wakupati, Bhaktapur',
                'latitude': 27.6725, 'longitude': 85.4325,
                'opening_hours': '6:00 AM - 8:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': False,
            },
            {
                'name': 'Dattatreya Temple',
                'slug': 'dattatreya-temple',
                'description': 'A large, two-tiered temple at Tachapal Tol, one of the oldest temples in Bhaktapur. Believed to have been built from a single tree trunk in the 12th century and dedicated to Dattatreya — a synthesis of Brahma, Vishnu, and Shiva.',
                'category': temples,
                'address': 'Tachapal Tol, Bhaktapur',
                'latitude': 27.6731, 'longitude': 85.4319,
                'opening_hours': '6:00 AM - 8:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': True,
            },
            {
                'name': 'Surya Binayak Temple',
                'slug': 'surya-binayak-temple',
                'description': 'A beloved Ganesh temple in a serene forest setting south of Bhaktapur, considered one of the four important Ganesh shrines of the Kathmandu Valley. Thousands of devotees visit on Tuesdays and Saturdays for blessings.',
                'category': temples,
                'address': 'Surya Binayak, Bhaktapur',
                'latitude': 27.6601, 'longitude': 85.4350,
                'opening_hours': '5:00 AM - 8:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': True,
            },
            {
                'name': 'Nava Durga Temple',
                'slug': 'nava-durga-temple',
                'description': 'The principal temple of the Nava Durga Dyochhen complex in Thimi, dedicated to the nine manifestations of Durga. The associated Nava Durga dance troupe, a living tradition of costumed deity dancers, is based here.',
                'category': temples,
                'address': 'Thimi, Bhaktapur',
                'latitude': 27.6780, 'longitude': 85.4050,
                'opening_hours': '6:00 AM - 7:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': False,
            },
            {
                'name': 'Bhimsen Temple (Tachapal)',
                'slug': 'bhimsen-temple-tachapal',
                'description': 'A three-storied temple at Dattatreya Square dedicated to Bhimsen, the god of merchants and traders. Particularly revered by the Newar business community. Notable for its ornate woodcarving and metalwork facade.',
                'category': temples,
                'address': 'Tachapal Tol, Bhaktapur',
                'latitude': 27.6729, 'longitude': 85.4316,
                'opening_hours': '6:00 AM - 8:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': False,
            },
            {
                'name': 'Mahakali Temple',
                'slug': 'mahakali-temple-bhaktapur',
                'description': 'A powerful goddess temple in Bhaktapur dedicated to Mahakali. The inner sanctum houses a fierce, gilded deity image and is a major pilgrimage site during Dashain festival when thousands of devotees offer worship.',
                'category': temples,
                'address': 'Chuping Galli, Bhaktapur',
                'latitude': 27.6705, 'longitude': 85.4260,
                'opening_hours': '5:00 AM - 8:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': False,
            },
            {
                'name': 'Pashupatinath Temple (Bhaktapur)',
                'slug': 'pashupatinath-bhaktapur',
                'description': 'A local replica of the famous Pashupatinath temple, this important Shiva shrine features a sacred Shiva lingam, cremation ghats on the Hanumante River bank, and a serene riverside setting popular for meditation.',
                'category': temples,
                'address': 'Hanumante Ghat, Bhaktapur',
                'latitude': 27.6735, 'longitude': 85.4230,
                'opening_hours': '5:00 AM - 9:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': False,
            },
            {
                'name': 'Yaksheswara Mahadev Temple',
                'slug': 'yaksheswara-temple',
                'description': 'An elegant temple at Bhaktapur Durbar Square with superb erotic woodcarvings on its roof struts, believed to ward off lightning. One of the most photographed architectural details in Bhaktapur.',
                'category': temples,
                'address': 'Durbar Square, Bhaktapur',
                'latitude': 27.6718, 'longitude': 85.4268,
                'opening_hours': '7:00 AM - 6:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': False,
            },
            # ── Heritage Sites ────────────────────────────────────────────
            {
                'name': 'Pottery Square (Kumale Tol)',
                'slug': 'pottery-square',
                'description': 'Experience the living tradition of Newari pottery-making at this outdoor workshop where local artisans hand-throw clay pots using ancient techniques passed down for generations. The juju dhau yoghurt pots and traditional water vessels are made here.',
                'category': heritage,
                'address': 'Pottery Square, Bhaktapur',
                'latitude': 27.6698, 'longitude': 85.4255,
                'opening_hours': '8:00 AM - 6:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': True,
            },
            {
                'name': 'Peacock Window (Pujari Math)',
                'slug': 'peacock-window',
                'description': 'Carved in the 15th century, the Peacock Window at Pujari Math in Dattatreya Square is considered one of the finest examples of woodcarving in Nepal. The intricate lattice of peacock feathers, gods, and mythological creatures is a masterpiece of Newari craftsmanship.',
                'category': heritage,
                'address': 'Tachapal Tol, Bhaktapur',
                'latitude': 27.6729, 'longitude': 85.4320,
                'opening_hours': 'Open 24 hours (exterior)',
                'is_free': True, 'entry_fee': None, 'is_featured': True,
            },
            {
                'name': '55-Window Palace',
                'slug': '55-window-palace',
                'description': 'The royal palace of the Malla kings, now partially housing the National Art Museum. Its southern facade features 55 elaborately carved windows across three floors, representing a pinnacle of Newari woodcarving. The palace dates to the late 17th century.',
                'category': heritage,
                'address': 'Durbar Square, Bhaktapur',
                'latitude': 27.6724, 'longitude': 85.4268,
                'opening_hours': '10:00 AM - 4:30 PM',
                'entry_fee': 200, 'is_free': False, 'is_featured': True,
            },
            {
                'name': 'Chyasilin Mandap',
                'slug': 'chyasilin-mandap',
                'description': 'An octagonal pavilion at Bhaktapur Durbar Square, rebuilt after the 1934 earthquake using its original stones. The eight-sided structure is used for royal ceremonies and is a fine example of Malla-period architecture.',
                'category': heritage,
                'address': 'Durbar Square, Bhaktapur',
                'latitude': 27.6721, 'longitude': 85.4273,
                'opening_hours': '7:00 AM - 7:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': False,
            },
            {
                'name': 'Nava Durga Dyochhen',
                'slug': 'nava-durga-dyochhen',
                'description': 'The sacred deity house (dyochhen) of the Nava Durga dance tradition in Bhaktapur, where the costumes and masks of the nine Durga deities are kept. The annual mask dance cycle is a UNESCO Intangible Cultural Heritage and runs from September to May.',
                'category': heritage,
                'address': 'Nava Durga Lane, Bhaktapur',
                'latitude': 27.6715, 'longitude': 85.4290,
                'opening_hours': '9:00 AM - 5:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': True,
            },
            {
                'name': 'Kumari Ghar (Bhaktapur)',
                'slug': 'kumari-ghar-bhaktapur',
                'description': 'Home of the living goddess Kumari of Bhaktapur — a young girl chosen through rigorous religious criteria to embody the goddess Taleju. The ornate building features traditional Newari latticed windows. Occasional public appearances on festival days.',
                'category': heritage,
                'address': 'Durbar Square, Bhaktapur',
                'latitude': 27.6719, 'longitude': 85.4272,
                'opening_hours': '7:00 AM - 6:00 PM (exterior)',
                'is_free': True, 'entry_fee': None, 'is_featured': False,
            },
            # ── Museums ───────────────────────────────────────────────────
            {
                'name': 'National Art Museum',
                'slug': 'national-art-museum-bhaktapur',
                'description': 'Housed in the former palace of King Bhupatindra Malla, this museum features a rich collection of Thangka paintings, woodcarvings, metal crafts, and medieval Newari art spanning over 1,500 years of artistic tradition.',
                'category': museums,
                'address': 'Durbar Square, Bhaktapur',
                'latitude': 27.6724, 'longitude': 85.4269,
                'opening_hours': '10:00 AM - 4:30 PM (Closed Tue)',
                'entry_fee': 200, 'is_free': False, 'is_featured': True,
            },
            {
                'name': 'Brass and Bronze Museum',
                'slug': 'brass-bronze-museum',
                'description': 'Located inside Pujari Math at Dattatreya Square, this museum displays an outstanding collection of traditional Newari bronze and brass household items — oil lamps, ritual vessels, water pots, and musical instruments — dating from the 12th to 20th centuries.',
                'category': museums,
                'address': 'Tachapal Tol, Bhaktapur',
                'latitude': 27.6730, 'longitude': 85.4321,
                'opening_hours': '10:00 AM - 4:30 PM (Closed Tue)',
                'entry_fee': 100, 'is_free': False, 'is_featured': True,
            },
            {
                'name': 'Woodcarving Museum',
                'slug': 'woodcarving-museum-bhaktapur',
                'description': 'Housed in a historic building at Dattatreya Square, this museum showcases the extraordinary woodcarving tradition of Bhaktapur with exhibits ranging from deity figures and window panels to temple struts and ritual objects.',
                'category': museums,
                'address': 'Tachapal Tol, Bhaktapur',
                'latitude': 27.6730, 'longitude': 85.4318,
                'opening_hours': '10:00 AM - 4:30 PM (Closed Tue)',
                'entry_fee': 100, 'is_free': False, 'is_featured': False,
            },
            {
                'name': 'Natural History Museum',
                'slug': 'natural-history-museum-bhaktapur',
                'description': 'A small but informative museum featuring flora and fauna of Nepal, geological specimens, and ethnographic items related to Bhaktapur and the Bagmati Province. Good for families and students learning about Nepal\'s biodiversity.',
                'category': museums,
                'address': 'Durbar Square area, Bhaktapur',
                'latitude': 27.6726, 'longitude': 85.4265,
                'opening_hours': '10:00 AM - 4:00 PM (Closed Tue)',
                'entry_fee': 50, 'is_free': False, 'is_featured': False,
            },
            # ── Parks & Gardens ───────────────────────────────────────────
            {
                'name': 'Sallaghari Park',
                'slug': 'sallaghari-park',
                'description': 'A scenic riverside park along the Hanumante River, popular with locals for morning walks, yoga, and picnics. Features gardens, a small children\'s play area, and pleasant pathways shaded by trees with views of the forested hillsides beyond.',
                'category': parks,
                'address': 'Sallaghari, Bhaktapur',
                'latitude': 27.6755, 'longitude': 85.4200,
                'opening_hours': '5:00 AM - 8:00 PM',
                'is_free': True, 'entry_fee': None, 'is_featured': False,
            },
            # ── Ponds & Water Bodies ──────────────────────────────────────
            {
                'name': 'Siddha Pokhari (Ram Pokhari)',
                'slug': 'siddha-pokhari',
                'description': 'A large, ancient royal pond at the western entrance of Bhaktapur, measuring 300 × 150 metres. The pond is surrounded by ghats, small shrines, and a beautiful garden. A peaceful spot for an early morning or evening walk with reflections of the city skyline.',
                'category': ponds,
                'address': 'Siddha Pokhari, Bhaktapur',
                'latitude': 27.6730, 'longitude': 85.4240,
                'opening_hours': 'Open 24 hours',
                'is_free': True, 'entry_fee': None, 'is_featured': True,
            },
            {
                'name': 'Kamal Pokhari',
                'slug': 'kamal-pokhari',
                'description': 'A lotus pond in the heart of Bhaktapur\'s old town, fringed by traditional Newari buildings and small shrines. The pond comes alive with pink lotus blossoms in summer and is a serene escape from the busy streets.',
                'category': ponds,
                'address': 'Kamal Pokhari, Bhaktapur',
                'latitude': 27.6708, 'longitude': 85.4278,
                'opening_hours': 'Open 24 hours',
                'is_free': True, 'entry_fee': None, 'is_featured': False,
            },
            # ── Sacred Sites ──────────────────────────────────────────────
            {
                'name': 'Mini Pashupati Complex',
                'slug': 'mini-pashupati-complex',
                'description': 'A cluster of small Shiva shrines along the Hanumante River bank, forming a miniature replica of Pashupatinath. Sacred cremation ghats where traditional Hindu rituals are performed. A deeply atmospheric site at dawn and dusk.',
                'category': sacred,
                'address': 'Hanumante River Bank, Bhaktapur',
                'latitude': 27.6740, 'longitude': 85.4225,
                'opening_hours': 'Open 24 hours',
                'is_free': True, 'entry_fee': None, 'is_featured': False,
            },
            {
                'name': 'Telkot & Nagarkot Road Viewpoint',
                'slug': 'telkot-nagarkot-viewpoint',
                'description': 'The scenic hilltop road from Bhaktapur to Nagarkot passes through Telkot, offering panoramic views of the Kathmandu Valley, Bhaktapur city, and on clear days the Himalayan peaks including Langtang and Ganesh Himal.',
                'category': sacred,
                'address': 'Telkot, Bhaktapur District',
                'latitude': 27.6950, 'longitude': 85.4600,
                'opening_hours': 'Open 24 hours',
                'is_free': True, 'entry_fee': None, 'is_featured': True,
            },
        ]
        for d in data:
            Attraction.objects.get_or_create(slug=d['slug'], defaults=d)

    def _businesses(self):
        from businesses.models import Business
        data = [
            # ── Restaurants ───────────────────────────────────────────────
            {
                'name': 'Peacock Restaurant',
                'slug': 'peacock-restaurant',
                'description': 'Authentic Newari cuisine with panoramic views of Bhaktapur Durbar Square. Famous for Juju Dhau (King of Yoghurt), Samay Baji platters, and Newari set meals. One of the top dining spots in Bhaktapur.',
                'category': 'restaurant',
                'address': 'Durbar Square Area, Bhaktapur',
                'latitude': 27.6722, 'longitude': 85.4275,
                'phone': '+977-1-6610999',
                'opening_hours': '8:00 AM - 9:00 PM',
                'is_featured': True,
            },
            {
                'name': 'Marco Polo Restaurant',
                'slug': 'marco-polo-restaurant',
                'description': 'International and Nepali cuisine popular with foreign tourists. Rooftop seating with city views. Known for good pizza, pasta, and traditional dal bhat. Friendly English-speaking staff.',
                'category': 'restaurant',
                'address': 'Sukuldhoka, Bhaktapur',
                'latitude': 27.6725, 'longitude': 85.4278,
                'phone': '+977-1-6613882',
                'opening_hours': '8:00 AM - 10:00 PM',
                'is_featured': True,
            },
            {
                'name': 'Newari Kitchen',
                'slug': 'newari-kitchen',
                'description': 'A family-run restaurant specializing in authentic Newari home cooking. Specialties include Bara (lentil pancakes), Choila (spiced grilled meat), Yomari, and seasonal Newari delicacies. Cooking demonstrations available on request.',
                'category': 'restaurant',
                'address': 'Pottery Square, Bhaktapur',
                'latitude': 27.6700, 'longitude': 85.4258,
                'phone': '+977-9841234501',
                'opening_hours': '9:00 AM - 9:00 PM',
                'is_featured': True,
            },
            {
                'name': 'Sunny Restaurant & Bar',
                'slug': 'sunny-restaurant-bar',
                'description': 'A popular rooftop restaurant near Durbar Square serving Nepali, Indian, and continental dishes. Wonderful views of the old town, cold beer, and live Newari folk music on weekends.',
                'category': 'restaurant',
                'address': 'Durbar Square Road, Bhaktapur',
                'latitude': 27.6723, 'longitude': 85.4272,
                'phone': '+977-1-6611234',
                'opening_hours': '8:00 AM - 10:00 PM',
                'is_featured': True,
            },
            {
                'name': 'Pagoda Restaurant',
                'slug': 'pagoda-restaurant',
                'description': 'Rooftop restaurant overlooking Taumadhi Square with direct views of the Nyatapola Temple. Serves Nepali set meals, momos, and thukpa. One of the best vantage points for watching the square come alive at sunrise.',
                'category': 'restaurant',
                'address': 'Taumadhi Square, Bhaktapur',
                'latitude': 27.6716, 'longitude': 85.4282,
                'phone': '+977-1-6614200',
                'opening_hours': '7:00 AM - 9:00 PM',
                'is_featured': True,
            },
            {
                'name': 'Heritage View Restaurant',
                'slug': 'heritage-view-restaurant',
                'description': 'A terrace restaurant with sweeping views of Bhaktapur\'s terracotta rooftops and temple spires. Menu features Nepali thali, continental breakfast, and fresh juices. Popular for sunset dining.',
                'category': 'restaurant',
                'address': 'Sukuldhoka, Bhaktapur',
                'latitude': 27.6726, 'longitude': 85.4280,
                'phone': '+977-9851234502',
                'opening_hours': '7:30 AM - 9:30 PM',
                'is_featured': False,
            },
            {
                'name': 'Traditional Newari Bhanchha',
                'slug': 'traditional-newari-bhanchha',
                'description': 'An authentic Newari dining hall serving the complete Samay Baji platter: beaten rice, Bara, Choila, Aalu Tama, Bodi, and Juju Dhau. No printed menu — eat what the locals eat, the way they have for centuries.',
                'category': 'restaurant',
                'address': 'Old Town Lane, Bhaktapur',
                'latitude': 27.6712, 'longitude': 85.4295,
                'phone': '+977-9861234503',
                'opening_hours': '6:00 AM - 8:00 PM',
                'is_featured': True,
            },
            {
                'name': 'Thimi Restaurant',
                'slug': 'thimi-restaurant',
                'description': 'Restaurant in the suburb of Thimi serving Newari cuisine with an emphasis on clay-pot cooking. Try the Thimi-style Bara and the excellent Haaku Chhoyla (water-buffalo choila). A short tempo ride from Bhaktapur city.',
                'category': 'restaurant',
                'address': 'Thimi, Bhaktapur Municipality',
                'latitude': 27.6780, 'longitude': 85.4060,
                'phone': '+977-9871234504',
                'opening_hours': '8:00 AM - 8:00 PM',
                'is_featured': False,
            },
            {
                'name': 'Dattatreya Restaurant',
                'slug': 'dattatreya-restaurant',
                'description': 'A cozy restaurant facing Dattatreya Square, offering front-row seats to the quiet rhythms of Bhaktapur\'s oldest plaza. Serves Nepali and continental food with excellent local butter tea and hand-ground coffee.',
                'category': 'restaurant',
                'address': 'Tachapal Tol, Bhaktapur',
                'latitude': 27.6732, 'longitude': 85.4320,
                'phone': '+977-9841234505',
                'opening_hours': '8:00 AM - 9:00 PM',
                'is_featured': False,
            },
            {
                'name': 'Angan Restaurant',
                'slug': 'angan-restaurant',
                'description': 'Set in a traditional Newari courtyard house (angan), this restaurant offers a deeply local atmosphere. Specialties include Newari feast platters, homemade raksi (millet wine), and slow-cooked Aalu Tama curry.',
                'category': 'restaurant',
                'address': 'Golmadhi, Bhaktapur',
                'latitude': 27.6712, 'longitude': 85.4302,
                'phone': '+977-9851234506',
                'opening_hours': '10:00 AM - 9:00 PM',
                'is_featured': False,
            },
            {
                'name': 'Luna Rooftop Restaurant',
                'slug': 'luna-rooftop-restaurant',
                'description': 'Bhaktapur\'s most romantic dining spot — a candlelit rooftop with views of Durbar Square at night. Serves continental cuisine, wood-fired pizza, and an excellent selection of Nepali wines and imported beers.',
                'category': 'restaurant',
                'address': 'Durbar Square Area, Bhaktapur',
                'latitude': 27.6720, 'longitude': 85.4270,
                'phone': '+977-9861234507',
                'opening_hours': '12:00 PM - 10:30 PM',
                'is_featured': True,
            },
            {
                'name': 'Dal Bhat Power Restaurant',
                'slug': 'dal-bhat-power-restaurant',
                'description': 'No-frills Nepali restaurant famous for unlimited dal bhat (lentil soup with rice, vegetables, and pickle). An institution for trekkers and locals. "Dal bhat power, 24 hour!" Excellent value at NPR 250–350.',
                'category': 'restaurant',
                'address': 'Sukuldhoka Road, Bhaktapur',
                'latitude': 27.6727, 'longitude': 85.4276,
                'phone': '+977-9841234508',
                'opening_hours': '6:00 AM - 9:00 PM',
                'is_featured': False,
            },
            {
                'name': 'Bishnu\'s Kitchen',
                'slug': 'bishnus-kitchen',
                'description': 'A beloved small restaurant run by a local family. Bishnu cooks everything fresh to order. Famous for her Thakali-style dal bhat, homemade achaar (pickle), and warm hospitality. Book ahead for the special Newari dinner set.',
                'category': 'restaurant',
                'address': 'Pottery Square Lane, Bhaktapur',
                'latitude': 27.6699, 'longitude': 85.4257,
                'phone': '+977-9871234509',
                'opening_hours': '7:00 AM - 8:00 PM',
                'is_featured': False,
            },
            {
                'name': 'Om\'s Home Restaurant',
                'slug': 'oms-home-restaurant',
                'description': 'A welcoming home-restaurant known for cooking classes and authentic Nepali meals in a family setting. Offers half-day cooking classes covering momos, dal bhat, and Newari dishes. Advance booking recommended.',
                'category': 'restaurant',
                'address': 'Old Bhaktapur Lane, Bhaktapur',
                'latitude': 27.6715, 'longitude': 85.4285,
                'phone': '+977-9801234510',
                'opening_hours': '8:00 AM - 9:00 PM',
                'is_featured': False,
            },
            # ── Cafés ─────────────────────────────────────────────────────
            {
                'name': 'Café Nyatapola',
                'slug': 'cafe-nyatapola',
                'description': 'Cozy café inside a 500-year-old merchant house with views of Taumadhi Square and the Nyatapola Temple. Serves Nepali butter tea, pour-over coffee, homemade cakes, and traditional snacks.',
                'category': 'cafe',
                'address': 'Taumadhi Square, Bhaktapur',
                'latitude': 27.6716, 'longitude': 85.4283,
                'phone': '+977-1-6614502',
                'opening_hours': '7:00 AM - 8:00 PM',
                'is_featured': True,
            },
            {
                'name': 'Namche Coffee & Kitchen',
                'slug': 'namche-coffee-kitchen',
                'description': 'A specialty coffee shop in Bhaktapur serving single-origin Nepali coffee from the Gulmi hills. Also serves excellent avocado toast, granola bowls, fresh juices, and smoothies. Popular with digital nomads and morning visitors.',
                'category': 'cafe',
                'address': 'Sukuldhoka, Bhaktapur',
                'latitude': 27.6724, 'longitude': 85.4277,
                'phone': '+977-9841234511',
                'opening_hours': '7:30 AM - 7:00 PM',
                'is_featured': True,
            },
            {
                'name': 'Durbar Café',
                'slug': 'durbar-cafe',
                'description': 'A relaxed café on the edge of Bhaktapur Durbar Square, ideal for resting tired feet after exploring. Serves filter coffee, masala chai, fresh momos, and sandwiches. Outdoor seating with views of the Golden Gate.',
                'category': 'cafe',
                'address': 'Durbar Square, Bhaktapur',
                'latitude': 27.6721, 'longitude': 85.4274,
                'phone': '+977-9851234512',
                'opening_hours': '7:00 AM - 7:30 PM',
                'is_featured': False,
            },
            {
                'name': 'Taumadhi Café',
                'slug': 'taumadhi-cafe',
                'description': 'A tiny but atmospheric café in a converted Newari house at the corner of Taumadhi Square. Famous for its homemade Juju Dhau served in clay pots, sel roti, and strong Nepali tea.',
                'category': 'cafe',
                'address': 'Taumadhi, Bhaktapur',
                'latitude': 27.6717, 'longitude': 85.4286,
                'phone': '+977-9861234513',
                'opening_hours': '6:30 AM - 7:00 PM',
                'is_featured': False,
            },
            {
                'name': 'Garden View Café',
                'slug': 'garden-view-cafe',
                'description': 'A peaceful café with a small garden courtyard near Siddha Pokhari. Serves organic herbal teas, fresh juices, and light Nepali snacks. A tranquil escape from the main tourist areas.',
                'category': 'cafe',
                'address': 'Siddha Pokhari Road, Bhaktapur',
                'latitude': 27.6728, 'longitude': 85.4243,
                'phone': '+977-9871234514',
                'opening_hours': '8:00 AM - 6:30 PM',
                'is_featured': False,
            },
            {
                'name': 'Kumari Café & Bakery',
                'slug': 'kumari-cafe-bakery',
                'description': 'A charming bakery-café near Durbar Square producing fresh bread, croissants, and cakes daily. Also serves espresso drinks, fresh fruit smoothies, and a popular Newari breakfast platter with Bara and eggs.',
                'category': 'cafe',
                'address': 'Durbar Square Lane, Bhaktapur',
                'latitude': 27.6719, 'longitude': 85.4269,
                'phone': '+977-9841234515',
                'opening_hours': '7:00 AM - 8:00 PM',
                'is_featured': False,
            },
            # ── Hotels ────────────────────────────────────────────────────
            {
                'name': 'Bhadgaon Guest House',
                'slug': 'bhadgaon-guest-house',
                'description': 'Charming heritage guesthouse steps from Durbar Square. Traditional Newari architecture with modern amenities, rooftop terrace with mountain views, and excellent in-house restaurant serving Newari cuisine.',
                'category': 'hotel',
                'address': 'Durbar Square, Bhaktapur 44800',
                'latitude': 27.6720, 'longitude': 85.4274,
                'phone': '+977-1-6612120',
                'opening_hours': 'Open 24 hours',
                'is_featured': True,
            },
            {
                'name': 'Shiva Guest House',
                'slug': 'shiva-guest-house',
                'description': 'A budget-friendly guesthouse inside the old city of Bhaktapur with clean rooms, hot showers, and a welcoming family atmosphere. Rooftop terrace with views of terracotta rooftops. Great base for exploring the heritage sites on foot.',
                'category': 'hotel',
                'address': 'Taumadhi, Bhaktapur',
                'latitude': 27.6716, 'longitude': 85.4281,
                'phone': '+977-9861234516',
                'opening_hours': 'Open 24 hours',
                'is_featured': False,
            },
            # ── Shops ─────────────────────────────────────────────────────
            {
                'name': 'Heritage Handicraft Shop',
                'slug': 'heritage-handicraft-shop',
                'description': 'Family-run shop selling authentic Bhaktapur handicrafts: hand-painted Thangka paintings, bronze sculptures, woodcarvings, traditional pottery, and Dhaka fabric. Fixed prices and certificates of authenticity available.',
                'category': 'shop',
                'address': 'Pottery Square, Bhaktapur',
                'latitude': 27.6699, 'longitude': 85.4253,
                'phone': '+977-9801234517',
                'opening_hours': '9:00 AM - 7:00 PM',
                'is_featured': False,
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
             'Police: 100 | Fire Brigade: 101 | Ambulance: 102 | Tourist Police: +977-1-4247041 | Bhaktapur Municipality: 977-01-6613957 / 977-01-6610096 | Hospital: Bhaktapur Hospital +977-1-6610798'),
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
                title=title,
                defaults={'category': category, 'content': content, 'is_active': True}
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

"""Seeds news, reviews, and itineraries. Run: venv/bin/python manage.py seed_content"""
import random
from django.core.management.base import BaseCommand
from django.utils.text import slugify

NEWS_ARTICLES = [
    {"title":"Bhaktapur Durbar Square Restoration Project Completed","category":"announcement","is_pinned":True,
     "summary":"The two-year UNESCO-funded restoration of the 55-Window Palace has been completed, with over 400 hand-carved wooden windows restored to their 18th-century condition.",
     "content":"Bhaktapur Municipality is proud to announce the successful completion of the two-year restoration of the 55-Window Palace at Bhaktapur Durbar Square. The project, co-funded by UNESCO and German Development Cooperation (GIZ), has restored more than 400 individual hand-carved wooden windows and lattice panels to their original 18th-century condition.\n\nMaster craftsmen from the Newar woodcarving tradition worked alongside international conservation experts to document and replicate traditional joinery techniques. Every piece of damaged wood was catalogued, and where replacement was necessary, aged sal wood seasoned for at least 15 years was used to match the original material.\n\nMayor Ram Prasad Giri said at the reopening ceremony: 'This restoration is not merely about bricks and timber — it is about the living culture of Bhaktapur. Each carved motif tells the story of our ancestors.' The palace is now fully open to visitors, and entry is included in the standard Bhaktapur heritage zone ticket."},
    {"title":"New Tourist Entry Regulations for Bhaktapur Heritage Zone","category":"announcement","is_pinned":True,
     "summary":"From 1 Shrawan 2082, all visitors must register digitally at entry gates. The fee structure has been revised to NPR 1,800 for foreign nationals.",
     "content":"Bhaktapur Municipality has announced updated entry regulations for the UNESCO-listed heritage zone, effective from 1 Shrawan 2082. All visitors will be required to scan a QR code at one of the six designated entry gates before entering the heritage area.\n\nThe digital registration system replaces the previous paper-ticket system and enables the municipality to monitor footfall in real time, ensuring that sensitive areas such as Taumadhi Square are never overcrowded. Visitors who register receive a digital pass valid for 48 hours, allowing re-entry without additional payment.\n\nThe revised fee structure: Foreign nationals NPR 1,800 (previously NPR 1,500), SAARC nationals NPR 400, and Nepali citizens remain free with a valid citizenship card. Children under 10 are exempt regardless of nationality. Revenue directly funds the Heritage Conservation Fund for restoration, craft apprenticeships, and monument maintenance."},
    {"title":"Bisket Jatra 2082 Preparations Begin — Full Festival Schedule Released","category":"event","is_pinned":False,
     "summary":"Bhaktapur's most spectacular festival, Bisket Jatra, will begin on 11 Chaitra 2082. The full 9-day chariot procession schedule has been released along with road closure notices.",
     "content":"Preparations for Bhaktapur's legendary Bisket Jatra festival are well under way, with the municipality confirming the full 9-day schedule beginning 11 Chaitra 2082. The Bisket Jatra chariot festival marks the Nepali New Year and is one of the most dramatic celebrations in the Kathmandu Valley.\n\nThe centrepiece is the chariot procession of Bhairava and Bhadrakali through the narrow lanes of Bhaktapur. This year, structural engineers have inspected and certified the two newly constructed chariots, standing at 12 metres and 9 metres respectively. Hundreds of community members will pull the chariots using thick ropes, a tradition unbroken for over 500 years.\n\nThe festival programme: erection of the ceremonial pole (Yosin) at Taumadhi Square on Day 1, chariot procession on Days 3-5, tug-of-war at Khalna Tole on Day 6, and the lowering of the pole on Day 9 marking the New Year. Major roads through the heritage zone will be closed to all motorised vehicles. Free shuttle services from Bhaktapur bus park will be provided."},
    {"title":"Water Supply Upgrade for Sukuldhoka Ward Completed","category":"development","is_pinned":False,
     "summary":"Ward No. 7 residents now receive 16 hours of piped water daily after the successful upgrade of the old distribution network under the KUKL expansion project.",
     "content":"Residents of Ward No. 7 (Sukuldhoka) can now access clean piped water for up to 16 hours per day following completion of the water supply upgrade, finished three weeks ahead of the original schedule. The project replaced 4.2 km of ageing pipes with high-density polyethylene (HDPE) pipes, dramatically reducing leakage and improving water pressure.\n\nThe upgrade was funded jointly by KUKL and Bhaktapur Municipality under the ADB-supported KUKL Integrated Infrastructure Development Project. A total of 842 households now have metered connections, and a new overhead reservoir with 100,000-litre capacity has been constructed near Bhrikuti School.\n\nWard Chair Sita Devi Shrestha said: 'For years residents had to store water in tanks and wake up at odd hours. Now families have reliable water for drinking, cooking, and sanitation.' The next phase covers Wards 11 and 12, scheduled to begin in Bhadra 2082."},
    {"title":"Bhaktapur Wins UNESCO Asia-Pacific Heritage Award 2082","category":"announcement","is_pinned":False,
     "summary":"The municipality has received the UNESCO Asia-Pacific Award for Cultural Heritage Conservation for the exemplary restoration of the Wakupati Narayan Temple complex at Dattatreya Square.",
     "content":"Bhaktapur Municipality has been honoured with the UNESCO Asia-Pacific Award for Cultural Heritage Conservation 2082 for the restoration of the Wakupati Narayan Temple complex at Dattatreya Square. The award was presented at a ceremony in Bangkok.\n\nThe restoration project, led by the Department of Archaeology in partnership with Bhaktapur Municipality, took 18 months and involved painstaking documentation and repair of the 15th-century temple damaged in the 2015 Gorkha earthquake.\n\nThe jury citation noted: 'The project stands out for its commitment to traditional craftsmanship, locally sourced materials, and meaningful engagement of the Newar community.' Mayor Giri dedicated the award to the master craftsmen of Bhaktapur: 'This honour belongs to the hands that shaped the stone and carved the wood.' The award plaque will be permanently displayed at the Bhaktapur Museum."},
    {"title":"Free Heritage Walking Tour Launched for Bhaktapur Residents","category":"tourism","is_pinned":False,
     "summary":"Every Saturday at 7:00 AM, Bhaktapur residents can join a free two-hour guided heritage walk through the old town, led by trained local guides from the Heritage Trail Programme.",
     "content":"Bhaktapur Municipality's Tourism Development Division has launched a free weekly heritage walking tour exclusively for residents. The tour runs every Saturday from 7:00 AM and covers key monuments over approximately two hours on foot.\n\nThe initiative, branded the 'Hamro Bhaktapur Heritage Walk', was designed after surveys showed many long-term residents had never visited several of the city's most significant monuments, including the Wakupati Narayan Temple and Til Mahadev Narayan Temple.\n\nEach walk is led by a certified guide from the Bhaktapur Heritage Trail Programme, a municipality-supported initiative that has certified 34 local guides since 2079. The route varies monthly to cover different neighbourhoods including Taumadhi, Dattatreya, Sukuldhoka, and Pottery Square. Free for all residents presenting a valid citizenship certificate or voter ID. Tea and Juju Dhau provided at the end of each walk."},
    {"title":"Road Repair Works: Kamal Binayak to Lokanthali — Traffic Advisory","category":"alert","is_pinned":False,
     "summary":"Major road repair works on the Kamal Binayak-Lokanthali section begin 15 Ashadh 2082. Expect traffic disruption for 6 weeks. Alternative routes are advised.",
     "content":"Bhaktapur Municipality's Infrastructure Division has issued a traffic advisory for planned resurfacing and drainage improvement works on the 3.2 km Kamal Binayak to Lokanthali road section. Works begin 15 Ashadh 2082 and are expected to complete within 6 weeks.\n\nThe project will resurface the deteriorated asphalt section, replace collapsed stormwater drains, and install new pedestrian footpaths with tactile paving. The contract has been awarded to Himalayan Construction Pvt. Ltd. Total project cost is NPR 3.2 crore, funded from the Municipal Infrastructure Development Fund.\n\nDuring construction, the road will be open to traffic in alternating one-way sections. Heavy vehicles (over 5 tonnes) should use the Ring Road via Thimi. Emergency vehicles will have priority passage at all times. Residents are advised to allow 20-30 extra minutes for commutes. Report concerns to the municipality helpline: 01-6610000."},
    {"title":"Thimi Kumari Festival: Dates Confirmed for Baisakh 2082","category":"event","is_pinned":False,
     "summary":"The renowned Thimi Sindur Jatra will be held on 1 Baisakh 2082. Over 30 chariots will parade through Thimi Ward in a vivid spectacle of vermilion powder and traditional music.",
     "content":"The Thimi Sindur Jatra — one of the most visually stunning festivals in the Kathmandu Valley — has been confirmed for 1 Baisakh 2082 (14 April 2026). The festival, unique to Thimi (Ward No. 19 of Bhaktapur), involves the simultaneous procession of more than 30 chariots through narrow streets in a riot of vermilion powder and ceremonial music.\n\nThe festival traces its origins to the Malla period (circa 12th century) and celebrates the deity Balkumari. The procession culminates in a mass throwing of sindur (vermilion powder) over the chariots and worshippers, creating an iconic scene that has attracted international photographers for decades.\n\nFor 2082, the municipality has added elevated viewing platforms along the main procession route and medical first-aid posts at four points. Photography from elevated positions is permitted; drone photography requires advance permission. Special bus services from Kathmandu will run from 4:00 AM."},
    {"title":"Bhaktapur Municipal Digital Services Portal Launched","category":"development","is_pinned":False,
     "summary":"Citizens can now apply for birth certificates, marriage registration, land use permits, and 14 other services online through the new Bhaktapur Digital Services Portal.",
     "content":"Bhaktapur Municipality has officially launched the Bhaktapur Digital Services Portal, enabling citizens to access 16 core municipal services online without visiting the municipality building. The portal accepts login via NID card or mobile OTP.\n\nServices now available digitally include: birth certificate application, marriage registration, citizenship recommendation letters, ward migration certificates, land use change permits, building permits for structures under 40m2, business registration certificates, and tax clearance certificates. Processing status can be tracked in real time, and approved documents can be downloaded with a digital seal.\n\nMunicipal Administrator Bikash Paudel explained: 'Our goal is that no citizen should have to take a day off work to obtain a simple certificate. Most straightforward applications are processed within 72 hours.' A dedicated helpline (+977-1-6615000) and in-person digital assistance desk are available for citizens unfamiliar with the online process."},
    {"title":"Monsoon 2082: Road Safety and Flood Advisory for Bhaktapur","category":"alert","is_pinned":False,
     "summary":"The municipality urges residents to avoid waterlogged roads, not to cross swollen streams, and to report blocked drains immediately via the 101 emergency helpline.",
     "content":"With the onset of the monsoon season, Bhaktapur Municipality's Disaster Risk Reduction Unit has issued its annual safety advisory. Heavy rainfall is forecast for Bhaktapur district, with the Department of Hydrology and Meteorology predicting above-average precipitation this year.\n\nKey safety guidance: Several roads in the hilly wards (17, 18, 19 — Nagarkot and Changunarayan corridor) are susceptible to landslides during heavy rainfall. Citizens are requested to clear the drain inlet in front of their property before the monsoon peak. The Hanumante River, which passes through Wards 6, 7, and 8, is prone to flash flooding during intense rainfall.\n\nUnder no circumstances should anyone attempt to cross the river on foot when it is flowing above knee height. Emergency contacts: 101 (municipality emergency), 100 (Nepal Police), 102 (Ambulance). The municipality has pre-positioned emergency supplies at three distribution points across the city."},
]

REVIEWS = [
    {"ct":"attraction","slug":"bhaktapur-durbar-square","user_n":0,"rating":5,"title":"The crown jewel of Nepal","comment":"Bhaktapur Durbar Square is simply breathtaking. Every corner reveals another carved masterpiece — the 55-Window Palace alone is worth the trip. Visiting at sunrise is an unforgettable experience."},
    {"ct":"attraction","slug":"bhaktapur-durbar-square","user_n":1,"rating":4,"title":"Magnificent heritage","comment":"Stunning architecture and incredibly well-preserved. The entry fee is worth every rupee — it goes directly to conservation. Go early morning to avoid tour groups."},
    {"ct":"attraction","slug":"nyatapola-temple","user_n":0,"rating":5,"title":"Most impressive pagoda in Nepal","comment":"Five tiers of perfect proportions rising above Taumadhi Square — no photo does it justice. The guardian statues on each terrace are fascinating. The square is wonderful for people-watching in the evenings."},
    {"ct":"attraction","slug":"nyatapola-temple","user_n":1,"rating":5,"title":"Architectural perfection","comment":"Built in 1702 and has never collapsed, even in the 1934 and 2015 earthquakes. That speaks to the brilliance of Newari engineering."},
    {"ct":"attraction","slug":"changu-narayan-temple","user_n":0,"rating":5,"title":"Nepal's oldest Vishnu temple","comment":"A UNESCO treasure that most visitors miss. The 5th-century stone carvings here predate the Malla period entirely. The hilltop location with valley views is spectacular. Hire a guide — without one you will miss the iconographic details."},
    {"ct":"attraction","slug":"pottery-square-bhaktapur","user_n":1,"rating":4,"title":"Living craft tradition","comment":"What makes Pottery Square special is that it is not a museum — potters still work here every morning using the same wheel techniques as their great-grandparents."},
    {"ct":"attraction","slug":"dattatreya-square","user_n":0,"rating":4,"title":"Quiet beauty, fewer crowds","comment":"Less visited than Durbar Square but equally rich. The Dattatreya Temple is said to be made from a single tree. The Peacock Window nearby is a must-see."},
    {"ct":"attraction","slug":"national-art-museum-bhaktapur","user_n":1,"rating":4,"title":"Hidden gem of Bhaktapur","comment":"Some extraordinary medieval thangkas, bronze sculptures, and manuscript illuminations. Not huge but very thoughtfully curated. Allow 90 minutes."},
    {"ct":"business","slug":"peacock-restaurant-bhaktapur","user_n":0,"rating":5,"title":"Best view in Bhaktapur","comment":"The rooftop terrace looking directly over Durbar Square is unbeatable. Come for sunset and you will understand why this place has been full for 20 years. The Newari set meal is excellent."},
    {"ct":"business","slug":"peacock-restaurant-bhaktapur","user_n":1,"rating":4,"title":"Great location, solid food","comment":"Reliable quality, good portions, and the square view makes any meal special. The buffalo momo is excellent. Book in advance for dinner."},
    {"ct":"business","slug":"cafe-nyatapola","user_n":0,"rating":5,"title":"The perfect cafe experience","comment":"A 400-year-old merchant house converted into a cafe — the architecture alone is incredible. The pour-over coffee is genuinely excellent and the yomari are homemade."},
    {"ct":"business","slug":"bhadgaon-guest-house","user_n":1,"rating":5,"title":"Most atmospheric stay in Bhaktapur","comment":"Woke up to temple bells and birdsong, two minutes walk from Durbar Square. The carved-wood interiors are stunning, the rooftop has Himalayan views on clear mornings."},
    {"ct":"business","slug":"marco-polo-restaurant-bhaktapur","user_n":0,"rating":4,"title":"Reliable and generous","comment":"Huge portions, great value dal bhat, and the staff always remember regulars. Good WiFi. Nothing fancy but honest, good food in a friendly atmosphere."},
    {"ct":"business","slug":"kumale-handicrafts","user_n":1,"rating":5,"title":"Authentic crafts, fair prices","comment":"The family has been making pottery in Bhaktapur for generations. Prices are transparent and fair — no haggling. They carefully packed my Thangka paintings for international travel."},
    {"ct":"business","slug":"hotel-heritage-bhaktapur","user_n":0,"rating":4,"title":"Excellent value in the old town","comment":"Great location, traditional Newari decor in the rooms, and the rooftop breakfast is a lovely way to start the day. The owner is incredibly helpful with recommendations."},
]

ITINERARIES = [
    {"title":"3-Day Bhaktapur Heritage Trail","days":3,"budget":5000,"interests":["heritage","temples","food"],"group_type":"couple","group_size":2,
     "plan":{"title":"3-Day Bhaktapur Heritage Trail","summary":"Three days of immersive heritage, temples, and Newari cuisine.","days":[
         {"day":1,"title":"Durbar Square & the Old Core","activities":["7:00 AM — Bhaktapur Durbar Square at sunrise","9:00 AM — Breakfast at Cafe Nyatapola","10:00 AM — Taumadhi Square and Nyatapola Temple","12:00 PM — Newari lunch at Peacock Restaurant","2:00 PM — National Art Museum in 55-Window Palace","6:30 PM — Sunset from Bhadgaon Guest House rooftop","7:30 PM — Dinner at Dattatreya Square area"]},
         {"day":2,"title":"Pottery Square & Craft Quarter","activities":["7:00 AM — Pottery Square at dawn — potters at work","9:30 AM — Dattatreya Square and Peacock Window","11:00 AM — Kumale Handicrafts shopping","12:30 PM — Lunch at Marco Polo Restaurant","2:00 PM — Walk the four historic squares heritage trail","4:00 PM — Newari cooking class (book in advance)"]},
         {"day":3,"title":"Changu Narayan & Departure","activities":["7:00 AM — Jeep taxi to Changu Narayan Temple","7:30 AM — Nepal's oldest Vishnu temple (5th century carvings)","9:30 AM — Walk down through Changu village (1.5 hrs)","12:00 PM — Juju Dhau (King Yoghurt) near Durbar Square","1:00 PM — Last shopping at Pottery Square","2:30 PM — Depart Bhaktapur"]}
     ]}},
    {"title":"5-Day Bhaktapur & Valley Explorer","days":5,"budget":12000,"interests":["temples","culture","photography","food"],"group_type":"friends","group_size":4,
     "plan":{"title":"5-Day Bhaktapur & Valley Explorer","summary":"Five days exploring Bhaktapur in depth with day trips to Nagarkot and Panauti.","days":[
         {"day":1,"title":"Arrival & Durbar Square","activities":["Afternoon arrival, check-in at heritage guesthouse","4:00 PM — First walk through Durbar Square","6:00 PM — Sunset from Nyatapola Temple steps","7:30 PM — Welcome dinner: full Newari feast"]},
         {"day":2,"title":"Deep Dive: Old Town","activities":["7:00 AM — Sunrise photography at Durbar Square","9:00 AM — Guided tour of all four historic squares","12:00 PM — Lunch at Cafe Nyatapola","2:00 PM — Woodcarving workshop near Dattatreya Square","5:00 PM — Pottery Square at closing time"]},
         {"day":3,"title":"Nagarkot Sunrise & Photography","activities":["4:30 AM — Jeep to Nagarkot for Himalayan sunrise","8:00 AM — Breakfast at Nagarkot viewpoint","10:00 AM — Nagarkot to Changu Narayan hiking trail (3-4 hrs)","2:00 PM — Visit Changu Narayan Temple","4:00 PM — Return to Bhaktapur"]},
         {"day":4,"title":"Day Trip: Panauti Medieval Town","activities":["8:00 AM — Bus to Panauti (45 min)","9:00 AM — Indreswor Mahadev Temple and river confluence","12:30 PM — Local lunch in Panauti","2:00 PM — Return to Bhaktapur, free afternoon shopping","7:00 PM — Farewell dinner at Peacock Restaurant"]},
         {"day":5,"title":"Last Morning & Markets","activities":["7:00 AM — Final morning walk through the old town","9:00 AM — Weekly haat bazaar (Saturdays)","11:00 AM — Last shopping: pottery, Thangka, Dhaka fabric, singing bowls","1:00 PM — Departure"]}
     ]}},
    {"title":"Weekend Bhaktapur Escape","days":2,"budget":3000,"interests":["heritage","food","crafts"],"group_type":"solo","group_size":1,
     "plan":{"title":"Weekend Bhaktapur Escape","summary":"A perfect two-day introduction to Bhaktapur for first-time visitors.","days":[
         {"day":1,"title":"Essential Bhaktapur","activities":["8:00 AM — Enter heritage zone via Kamal Binayak gate","8:30 AM — Bhaktapur Durbar Square: Golden Gate, 55-Window Palace","11:00 AM — Taumadhi Square and Nyatapola Temple","12:30 PM — Lunch at Peacock Restaurant (rooftop)","2:00 PM — Dattatreya Square and Woodcarving Museum","4:00 PM — Pottery Square: watch potters, buy a handmade pot","7:30 PM — Dinner: yomari at Cafe Nyatapola"]},
         {"day":2,"title":"Temples & Crafts","activities":["7:00 AM — Sunrise walk through deserted old-town streets","8:00 AM — Neighbourhood temples: Til Mahadev, Wakupati Narayan","10:00 AM — Shopping at Kumale Handicrafts","11:30 AM — Street food: chatamari, juju dhau","1:00 PM — Final stroll through Durbar Square","2:00 PM — Departure"]}
     ]}},
]


class Command(BaseCommand):
    help = "Seed news articles, reviews, and itineraries"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=== Seeding Content ==="))
        self._news()
        self._reviews()
        self._itineraries()
        self.stdout.write(self.style.SUCCESS("\nDone!"))

    def _news(self):
        from news.models import NewsArticle
        from accounts.models import User
        self.stdout.write(self.style.MIGRATE_HEADING("\n[1/3] News articles…"))
        try:
            author = User.objects.get(email="admin@bhaktapur.gov.np")
        except User.DoesNotExist:
            author = None
        for item in NEWS_ARTICLES:
            slug = slugify(item["title"])[:48]
            art, created = NewsArticle.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": item["title"],
                    "summary": item["summary"],
                    "content": item["content"],
                    "category": item["category"],
                    "is_pinned": item.get("is_pinned", False),
                    "is_active": True,
                    "author": author,
                    "view_count": random.randint(120, 4800),
                }
            )
            self.stdout.write(f"  {'Created' if created else 'Updated'}: {art.title[:55]}")

    def _reviews(self):
        from reviews.models import Review
        from tourism.models import Attraction
        from businesses.models import Business
        from accounts.models import User
        self.stdout.write(self.style.MIGRATE_HEADING("\n[2/3] Reviews…"))
        users = []
        for email, fn, ln, uname in [
            ("tourist1@test.com", "Priya", "Sharma", "tourist1"),
            ("tourist2@test.com", "David", "Wilson", "tourist2"),
        ]:
            u, created = User.objects.get_or_create(
                email=email,
                defaults={"first_name": fn, "last_name": ln, "username": uname}
            )
            if created:
                u.set_password("Tourist@123")
                u.save()
            users.append(u)
        attrs = {a.slug: a for a in Attraction.objects.all()}
        bizs  = {b.slug: b for b in Business.objects.all()}
        for item in REVIEWS:
            user = users[item["user_n"]]
            obj  = (attrs if item["ct"] == "attraction" else bizs).get(item["slug"])
            if not obj:
                pool = attrs if item["ct"] == "attraction" else bizs
                obj = next((v for k, v in pool.items() if item["slug"] in k), None)
            if not obj:
                self.stdout.write(self.style.WARNING(f"  Skip: {item['slug']}"))
                continue
            r, created = Review.objects.get_or_create(
                user=user, content_type=item["ct"], object_id=obj.pk,
                defaults={"rating": item["rating"], "title": item["title"],
                          "comment": item["comment"], "is_approved": True,
                          "helpful_count": random.randint(0, 45)}
            )
            self.stdout.write(f"  {'Created' if created else 'Exists'}: {item['ct']} — {obj.name[:35]}")

    def _itineraries(self):
        from itinerary.models import Itinerary
        from accounts.models import User
        self.stdout.write(self.style.MIGRATE_HEADING("\n[3/3] Itineraries…"))
        try:
            user = User.objects.get(email="tourist1@test.com")
        except User.DoesNotExist:
            self.stdout.write(self.style.WARNING("  tourist1@test.com not found — run after reviews step"))
            return
        for item in ITINERARIES:
            it, created = Itinerary.objects.get_or_create(
                user=user, title=item["title"],
                defaults={"days": item["days"], "budget": item["budget"],
                          "budget_currency": "NPR", "interests": item["interests"],
                          "group_type": item["group_type"], "group_size": item["group_size"],
                          "generated_plan": item["plan"], "is_saved": True}
            )
            self.stdout.write(f"  {'Created' if created else 'Exists'}: {item['title']}")

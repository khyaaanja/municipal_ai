from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Itinerary
import json
import re


def _generate_default_plan(days, budget="", group_type="solo", interests=None):
    """
    Generate a complete itinerary plan without calling AI.
    Uses structured template-based data for real Bhaktapur locations.
    Acts as fallback when Groq API is unavailable/quota-exceeded.
    """
    interests = interests or []
    interest_set = set(i.lower() for i in interests)

    TEMPLATE_STOPS = [
        {
            "day_offset": 0,
            "stops": [
                {"time": "8:00 AM", "activity": "Breakfast at a local Newari cafe - try samay baji", "location": "Taumadhi Square", "duration": "1 hour", "cost": "NPR 300"},
                {"time": "9:00 AM", "activity": "Explore Bhaktapur Durbar Square - 55 Window Palace, Golden Gate", "location": "Durbar Square", "duration": "2.5 hours", "cost": "NPR 1500"},
                {"time": "11:30 AM", "activity": "Visit Nyatapola Temple - tallest pagoda in Nepal", "location": "Taumadhi Square", "duration": "45 min", "cost": "Free"},
                {"time": "12:30 PM", "activity": "Lunch at the famous Yalamul or a rooftop restaurant", "location": "Durbar Square area", "duration": "1 hour", "cost": "NPR 600"},
                {"time": "2:00 PM", "activity": "Walk through Pottery Square - watch artisans at work", "location": "Pottery Square", "duration": "1 hour", "cost": "Free"},
                {"time": "3:30 PM", "activity": "Browse Dattatreya Square and the Peacock Window", "location": "Dattatreya Square", "duration": "1 hour", "cost": "Free"},
                {"time": "5:00 PM", "activity": "Stroll along the old city alleyways and photograph traditional Newari architecture", "location": "Bhaktapur Old City", "duration": "1 hour", "cost": "Free"},
                {"time": "6:30 PM", "activity": "Sunset at a rooftop cafe overlooking the city", "location": "Bhaktapur", "duration": "1 hour", "cost": "NPR 400"},
            ]
        },
        {
            "day_offset": 1,
            "stops": [
                {"time": "7:30 AM", "activity": "Morning walk to Surya Vinayak Temple - ancient Ganesh shrine", "location": "Surya Vinayak", "duration": "1 hour", "cost": "Free"},
                {"time": "9:00 AM", "activity": "Visit Changu Narayan Temple - UNESCO site, oldest in Kathmandu Valley", "location": "Changu Narayan", "duration": "2 hours", "cost": "NPR 500"},
                {"time": "11:30 AM", "activity": "Explore the Bhaktapur National Art Gallery", "location": "Durbar Square", "duration": "1 hour", "cost": "NPR 200"},
                {"time": "1:00 PM", "activity": "Lunch at a traditional Newari restaurant - try juju dhau (king yogurt)", "location": "Pottery Square area", "duration": "1 hour", "cost": "NPR 500"},
                {"time": "2:30 PM", "activity": "Take a pottery workshop - learn from master potters", "location": "Pottery Square", "duration": "2 hours", "cost": "NPR 800"},
                {"time": "5:00 PM", "activity": "Visit the Bhairavnath Temple and surrounding squares", "location": "Taumadhi", "duration": "1 hour", "cost": "Free"},
                {"time": "7:00 PM", "activity": "Evening aarti at a local temple", "location": "Near Durbar Square", "duration": "30 min", "cost": "Free"},
            ]
        },
        {
            "day_offset": 2,
            "stops": [
                {"time": "8:00 AM", "activity": "Visit Nagarkot viewpoint - panoramic Himalayan views", "location": "Nagarkot", "duration": "3 hours", "cost": "NPR 500"},
                {"time": "11:30 AM", "activity": "Return to Bhaktapur and visit the Woodcarving Museum", "location": "Durbar Square", "duration": "1 hour", "cost": "NPR 200"},
                {"time": "1:00 PM", "activity": "Lunch - sample local specialties: chatamari, bara, wo", "location": "Taumadhi", "duration": "1 hour", "cost": "NPR 400"},
                {"time": "2:30 PM", "activity": "Explore Thimi - ancient pottery and mask-making town", "location": "Thimi (Madhyapur)", "duration": "2 hours", "cost": "Free"},
                {"time": "5:00 PM", "activity": "Visit the Bhaktapur Handicraft Center for souvenirs", "location": "Bhaktapur", "duration": "1 hour", "cost": "Free"},
                {"time": "7:00 PM", "activity": "Farewell dinner - traditional Newari feast (bhoye)", "location": "Traditional restaurant", "duration": "1.5 hours", "cost": "NPR 1000"},
            ]
        },
    ]

    extra_day_template = [
        {"time": "9:00 AM", "activity": "Guided heritage walk through a Bhaktapur neighbourhood", "location": "Bhaktapur", "duration": "2 hours", "cost": "NPR 500"},
        {"time": "12:00 PM", "activity": "Cooking class - learn to make momos and Newari dishes", "location": "Local home kitchen", "duration": "2 hours", "cost": "NPR 1200"},
        {"time": "3:00 PM", "activity": "Free time to explore or shop for souvenirs", "location": "Bhaktapur", "duration": "2 hours", "cost": "Free"},
        {"time": "6:00 PM", "activity": "Cultural show with traditional Newari music and dance", "location": "Bhaktapur", "duration": "1.5 hours", "cost": "NPR 600"},
    ]

    if "food" in interest_set or "culinary" in interest_set:
        for day_data in TEMPLATE_STOPS:
            day_data["stops"].append(
                {"time": "4:00 PM", "activity": "Food walk - sample juju dhau, chatamari, bara, and samosa from street vendors", "location": "Bhaktapur lanes", "duration": "2 hours", "cost": "NPR 400"}
            )

    if "photography" in interest_set:
        TEMPLATE_STOPS[0]["stops"].append(
            {"time": "6:00 AM", "activity": "Golden hour photography walk - empty squares and morning light", "location": "Durbar Square", "duration": "1.5 hours", "cost": "Free"}
        )

    if "culture" in interest_set or "history" in interest_set:
        extra_stops = [
            {"time": "10:00 AM", "activity": "Guided tour with a local historian explaining Newari architecture", "location": "Durbar Square", "duration": "2 hours", "cost": "NPR 800"},
            {"time": "4:00 PM", "activity": "Visit a traditional Newari home to understand daily life", "location": "Residential area", "duration": "1 hour", "cost": "Free"},
        ]
        TEMPLATE_STOPS[1]["stops"].extend(extra_stops)

    plan = []
    for i in range(days):
        if i < len(TEMPLATE_STOPS):
            day_stops = TEMPLATE_STOPS[i]["stops"]
        else:
            day_stops = extra_day_template

        if i == 0:
            title = "Day 1 - Heritage Immersion in Bhaktapur"
        elif i == 1:
            title = "Day 2 - Temples, Art, and Culture"
        elif i == 2:
            title = "Day 3 - Views, Crafts, and Culinary Delights"
        else:
            title = f"Day {i+1} - Exploring Bhaktapur"

        plan.append({"day": i + 1, "title": title, "stops": day_stops})

    return plan


@login_required
def itinerary_list(request):
    itineraries = Itinerary.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "itinerary/list.html", {"itineraries": itineraries})


@login_required
def itinerary_detail(request, pk):
    itin = get_object_or_404(Itinerary, pk=pk, user=request.user)
    return render(request, "itinerary/detail.html", {"itinerary": itin})


@login_required
def generate_itinerary(request):
    if request.method != "POST":
        return JsonResponse({"success": False}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    days = min(max(int(data.get("days", 3)), 1), 14)
    budget = data.get("budget", "")
    group_type = data.get("group_type", "solo")
    interests = data.get("interests", [])

    plan = None
    ai_used = False
    try:
        from chatbot.ai_engine import MunicipalAIEngine
        engine = MunicipalAIEngine()
        prompt = (
            f"Generate a detailed {days}-day itinerary for {group_type} visiting Bhaktapur, Nepal. "
            f"Budget: NPR {budget if budget else 'flexible'}. "
            f"Interests: {', '.join(interests) if interests else 'general sightseeing'}. "
            "Return ONLY valid JSON array where each element has: "
            '{"day": 1, "title": "Day title", "stops": [{"time": "9:00 AM", "activity": "...", "location": "...", "duration": "1 hour", "cost": "NPR 200"}]}. '
            "Use only real Bhaktapur locations from the database."
        )
        result = engine.chat(prompt, conversation_history=[])
        json_match = re.search(r"\[.*\]", result["response"], re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list) and len(parsed) > 0:
                plan = parsed
                ai_used = True
    except Exception:
        pass

    if plan is None:
        plan = _generate_default_plan(days, budget, group_type, interests)

    title = f"{days}-Day {group_type.title()} Itinerary - {', '.join(i.title() for i in interests[:2]) or 'Bhaktapur'}"
    itin = Itinerary.objects.create(
        user=request.user,
        title=title,
        days=days,
        budget=float(budget) if budget else None,
        group_type=group_type,
        interests=interests,
        generated_plan=plan,
    )
    return JsonResponse({"success": True, "itinerary_id": itin.pk, "ai_generated": ai_used})


@login_required
def delete_itinerary(request, pk):
    itin = get_object_or_404(Itinerary, pk=pk, user=request.user)
    if request.method == "POST":
        itin.delete()
        return JsonResponse({"success": True})
    return JsonResponse({"success": False}, status=405)

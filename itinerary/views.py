from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Itinerary
import json


@login_required
def itinerary_list(request):
    itineraries = Itinerary.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'itinerary/list.html', {'itineraries': itineraries})


@login_required
def itinerary_detail(request, pk):
    itin = get_object_or_404(Itinerary, pk=pk, user=request.user)
    return render(request, 'itinerary/detail.html', {'itinerary': itin})


@login_required
def generate_itinerary(request):
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    days = int(data.get('days', 3))
    budget = data.get('budget', '')
    group_type = data.get('group_type', 'solo')
    interests = data.get('interests', [])

    # Use AI engine to generate
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
    try:
        result = engine.chat(prompt, conversation_history=[])
        # Try to parse JSON from response
        import re
        json_match = re.search(r'\[.*\]', result['response'], re.DOTALL)
        if json_match:
            plan = json.loads(json_match.group())
        else:
            plan = [{"day": i+1, "title": f"Day {i+1} in Bhaktapur", "stops": [
                {"time": "9:00 AM", "activity": "Visit Bhaktapur Durbar Square", "location": "Durbar Square", "duration": "2 hours", "cost": "NPR 1500"},
                {"time": "12:00 PM", "activity": "Lunch at local Newari restaurant", "location": "Taumadhi", "duration": "1 hour", "cost": "NPR 500"},
                {"time": "2:00 PM", "activity": "Nyatapola Temple visit", "location": "Taumadhi Square", "duration": "1 hour", "cost": "Free"},
            ]} for i in range(days)]
    except Exception:
        plan = [{"day": i+1, "title": f"Day {i+1} in Bhaktapur", "stops": [
            {"time": "9:00 AM", "activity": "Visit Bhaktapur Durbar Square", "location": "Durbar Square", "duration": "2 hours", "cost": "NPR 1500"},
            {"time": "12:00 PM", "activity": "Juju Dhau tasting at Pottery Square", "location": "Pottery Square", "duration": "30 min", "cost": "NPR 150"},
        ]} for i in range(days)]

    title = f"{days}-Day {group_type.title()} Itinerary — {', '.join(i.title() for i in interests[:2]) or 'Bhaktapur'}"
    itin = Itinerary.objects.create(
        user=request.user,
        title=title,
        days=days,
        budget=float(budget) if budget else None,
        group_type=group_type,
        interests=interests,
        generated_plan=plan,
    )
    return JsonResponse({'success': True, 'itinerary_id': itin.pk})


@login_required
def delete_itinerary(request, pk):
    itin = get_object_or_404(Itinerary, pk=pk, user=request.user)
    if request.method == 'POST':
        itin.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False}, status=405)

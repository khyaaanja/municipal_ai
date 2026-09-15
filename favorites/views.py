from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Favorite
import json


def _resolve_favorites(favorites):
    """Attach name and url to each Favorite — bulk loads per type to avoid N+1."""
    from tourism.models import Attraction
    from events.models import Event
    from businesses.models import Business
    from marketplace.models import Product

    model_map = {
        'attraction': (Attraction, '/attractions/', 'slug'),
        'event':      (Event,      '/events/',      'slug'),
        'business':   (Business,   '/businesses/',  'slug'),
        'product':    (Product,    '/marketplace/', None),
    }

    # Group by type, bulk-fetch, build lookup dicts
    by_type: dict = {}
    for fav in favorites:
        by_type.setdefault(fav.content_type, []).append(fav.object_id)

    cache: dict = {}
    for ctype, ids in by_type.items():
        if ctype not in model_map:
            continue
        model_cls, _, _ = model_map[ctype]
        for obj in model_cls.objects.filter(pk__in=ids):
            cache[(ctype, obj.pk)] = obj

    resolved = []
    for fav in favorites:
        info = model_map.get(fav.content_type)
        obj = cache.get((fav.content_type, fav.object_id))
        if info and obj:
            _, url_prefix, slug_field = info
            slug_val = getattr(obj, slug_field) if slug_field else fav.object_id
            fav.object_name = str(obj)
            fav.object_url = f"{url_prefix}{slug_val}/"
        else:
            fav.object_name = '(Deleted)'
            fav.object_url = '#'
        resolved.append(fav)
    return resolved


@login_required
def favorites_list(request):
    all_favs = list(Favorite.objects.filter(user=request.user).order_by('-created_at'))
    all_favs = _resolve_favorites(all_favs)

    attractions = [f for f in all_favs if f.content_type == 'attraction']
    events      = [f for f in all_favs if f.content_type == 'event']
    businesses  = [f for f in all_favs if f.content_type == 'business']
    products    = [f for f in all_favs if f.content_type == 'product']

    return render(request, 'favorites/list.html', {
        'favorites':   all_favs,
        'attractions': attractions,
        'events':      events,
        'businesses':  businesses,
        'products':    products,
        'total_count': len(all_favs),
    })


@login_required
def toggle_favorite(request):
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=405)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST.dict()

    # Remove by primary key (from the favorites list page)
    favorite_id = data.get('favorite_id')
    if favorite_id:
        try:
            fav = Favorite.objects.get(id=int(favorite_id), user=request.user)
            fav.delete()
            return JsonResponse({'success': True, 'action': 'removed'})
        except Favorite.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Not found'}, status=404)

    # Toggle by content_type string + object_id
    content_type_str = data.get('content_type', '')
    object_id = data.get('object_id')

    valid_types = {'attraction', 'business', 'event', 'product'}
    if content_type_str not in valid_types or not object_id:
        return JsonResponse({'success': False, 'error': 'Invalid parameters'}, status=400)

    fav, created = Favorite.objects.get_or_create(
        user=request.user,
        content_type=content_type_str,
        object_id=int(object_id),
    )
    if not created:
        fav.delete()
        return JsonResponse({'success': True, 'action': 'removed'})
    return JsonResponse({'success': True, 'action': 'added'})

import json
from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.core.cache import cache

_HOMEPAGE_CACHE_KEY = 'homepage_context'
_HOMEPAGE_TTL = 300  # 5 minutes


def homepage(request):
    from tourism.models import Attraction
    from events.models import Event
    from businesses.models import Business
    from marketplace.models import Product
    from news.models import NewsArticle
    from django.utils import timezone

    ctx = cache.get(_HOMEPAGE_CACHE_KEY)
    if ctx is None:
        today = timezone.now().date()
        ctx = {
            'featured_attractions': list(Attraction.objects.filter(is_active=True, is_featured=True)[:6]),
            'today_events': list(Event.objects.filter(is_active=True, start_date__date=today)[:4]),
            'upcoming_events': list(Event.objects.filter(is_active=True, start_date__date__gte=today).order_by('start_date')[:4]),
            'popular_businesses': list(Business.objects.filter(is_active=True, is_featured=True)[:6]),
            'new_products': list(Product.objects.filter(is_active=True)[:8]),
            'latest_news': list(NewsArticle.objects.filter(is_active=True)[:4]),
        }
        cache.set(_HOMEPAGE_CACHE_KEY, ctx, _HOMEPAGE_TTL)
    return render(request, 'core/homepage.html', ctx)


def global_search(request):
    query = request.GET.get('q', '').strip()
    context = {'query': query, 'total_count': 0}

    if query:
        from tourism.models import Attraction
        from events.models import Event
        from businesses.models import Business
        from marketplace.models import Product
        from news.models import NewsArticle

        attractions = Attraction.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query), is_active=True
        )[:8]
        events = Event.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query), is_active=True
        )[:8]
        businesses = Business.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query), is_active=True
        )[:8]
        products = Product.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query), is_active=True
        )[:8]
        news = NewsArticle.objects.filter(
            Q(title__icontains=query) | Q(content__icontains=query), is_active=True
        )[:8]

        total_count = (
            attractions.count() + events.count() +
            businesses.count() + products.count() + news.count()
        )
        context.update({
            'attractions': attractions,
            'events': events,
            'businesses': businesses,
            'products': products,
            'news': news,
            'total_count': total_count,
        })

    return render(request, 'core/search.html', context)


def map_view(request):
    from tourism.models import Attraction
    from businesses.models import Business
    from events.models import Event
    from django.utils import timezone

    map_data = []

    for a in Attraction.objects.filter(
        is_active=True, latitude__isnull=False, longitude__isnull=False
    ).select_related('category'):
        map_data.append({
            'id': f'attr_{a.pk}',
            'name': a.name,
            'type': 'attraction',
            'lat': float(a.latitude),
            'lng': float(a.longitude),
            'address': a.address or '',
            'url': f'/attractions/{a.slug}/',
            'category': a.category.name if a.category else 'Attraction',
            'opening_hours': a.opening_hours or '',
            'entry_fee': f'NPR {a.entry_fee}' if a.entry_fee and not a.is_free else ('Free Entry' if a.is_free else ''),
            'is_featured': a.is_featured,
            'desc': a.description[:120] if a.description else '',
            'rating': None,
            'phone': a.phone or '',
        })

    for b in Business.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False):
        btype = 'food' if b.category in ('restaurant', 'cafe') else (
                'hotel' if b.category == 'hotel' else 'business')
        map_data.append({
            'id': f'biz_{b.pk}',
            'name': b.name,
            'type': btype,
            'lat': float(b.latitude),
            'lng': float(b.longitude),
            'address': b.address or '',
            'url': f'/businesses/{b.slug}/',
            'category': b.get_category_display(),
            'opening_hours': b.opening_hours or '',
            'rating': round(b.avg_rating, 1) if b.avg_rating else None,
            'phone': b.phone or '',
            'is_featured': b.is_featured,
            'is_verified': b.is_verified,
            'entry_fee': '',
            'desc': b.description[:120] if b.description else '',
        })

    for e in Event.objects.filter(
        is_active=True, start_date__gte=timezone.now(),
        latitude__isnull=False, longitude__isnull=False
    ):
        map_data.append({
            'id': f'event_{e.pk}',
            'name': e.name,
            'type': 'event',
            'lat': float(e.latitude),
            'lng': float(e.longitude),
            'address': e.venue or '',
            'url': f'/events/{e.slug}/',
            'category': e.get_category_display(),
            'opening_hours': e.start_date.strftime('%b %d, %Y · %I:%M %p'),
            'entry_fee': f'NPR {e.entry_fee}' if e.entry_fee and not e.is_free else ('Free' if e.is_free else ''),
            'is_featured': e.is_featured,
            'desc': e.description[:120] if e.description else '',
            'rating': None,
            'phone': '',
        })

    return render(request, 'core/map.html', {'map_data': json.dumps(map_data)})


@login_required
def orders_view(request):
    from marketplace.models import Order
    orders = Order.objects.filter(user=request.user).prefetch_related('items__product').order_by('-created_at')
    return render(request, 'core/orders.html', {'orders': orders})


def handler404(request, exception=None):
    from django.shortcuts import render as _render
    return _render(request, '404.html', status=404)

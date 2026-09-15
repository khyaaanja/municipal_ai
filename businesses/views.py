from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Avg
from django.core.paginator import Paginator
from django.core.cache import cache
from .models import Business


def businesses_list(request):
    category = request.GET.get('category', '')
    query    = request.GET.get('q', '').strip()
    page_num = request.GET.get('page', '1')

    # Cache anonymous, unfiltered first-page results for 10 minutes
    _cache_key = None
    if not request.user.is_authenticated and not query and page_num == '1':
        _cache_key = f'businesses_list:{category or "all"}'
        _cached = cache.get(_cache_key)
        if _cached:
            return _cached

    businesses = Business.objects.filter(is_active=True).select_related('owner')

    if category:
        businesses = businesses.filter(category=category)
    if query:
        businesses = businesses.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )

    paginator = Paginator(businesses, 12)
    page_obj  = paginator.get_page(page_num)
    params    = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    response = render(request, 'businesses/list.html', {
        'businesses': page_obj,
        'page_obj': page_obj,
        'querystring': querystring,
        'active_category': category,
        'query': query,
        'categories': Business.CATEGORY_CHOICES,
    })
    if _cache_key:
        cache.set(_cache_key, response, 600)
    return response


def business_detail(request, slug):
    business = get_object_or_404(Business, slug=slug, is_active=True)
    from reviews.models import Review
    reviews = Review.objects.filter(
        content_type='business', object_id=business.pk, is_approved=True
    ).order_by('-created_at')

    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg']

    return render(request, 'businesses/detail.html', {
        'business': business,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'menu_items': [],
    })

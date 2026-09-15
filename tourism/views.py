from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Avg
from django.core.paginator import Paginator
from django.core.cache import cache
from .models import Attraction, AttractionCategory


def attractions_list(request):
    category = request.GET.get('category', '')
    query    = request.GET.get('q', '').strip()
    page_num = request.GET.get('page', '1')

    _cache_key = None
    if not request.user.is_authenticated and not query and page_num == '1':
        _cache_key = f'attractions_list:{category or "all"}'
        _cached = cache.get(_cache_key)
        if _cached:
            return _cached

    attractions = Attraction.objects.filter(is_active=True).select_related('category').prefetch_related('images')
    if category:
        attractions = attractions.filter(category__slug=category)
    if query:
        attractions = attractions.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )

    categories = AttractionCategory.objects.all()

    paginator = Paginator(attractions, 12)
    page_obj  = paginator.get_page(page_num)
    params    = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    response = render(request, 'tourism/list.html', {
        'attractions': page_obj,
        'page_obj': page_obj,
        'querystring': querystring,
        'categories': categories,
        'active_category': category,
        'selected_category': category,
        'query': query,
    })
    if _cache_key:
        cache.set(_cache_key, response, 600)  # 10 minutes — attractions rarely change
    return response


def attraction_detail(request, slug):
    attraction = get_object_or_404(Attraction, slug=slug, is_active=True)
    from reviews.models import Review
    reviews = Review.objects.filter(
        content_type='attraction', object_id=attraction.pk, is_approved=True
    ).order_by('-created_at')

    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg']

    return render(request, 'tourism/detail.html', {
        'attraction': attraction,
        'reviews': reviews,
        'avg_rating': avg_rating,
    })

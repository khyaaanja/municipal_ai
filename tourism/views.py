from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Avg
from .models import Attraction, AttractionCategory


def attractions_list(request):
    category = request.GET.get('category', '')
    query = request.GET.get('q', '').strip()

    attractions = Attraction.objects.filter(is_active=True).select_related('category')
    if category:
        attractions = attractions.filter(category__slug=category)
    if query:
        attractions = attractions.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )

    categories = AttractionCategory.objects.all()

    return render(request, 'tourism/list.html', {
        'attractions': attractions,
        'categories': categories,
        'active_category': category,
        'query': query,
    })


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

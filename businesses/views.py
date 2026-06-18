from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Avg
from .models import Business


def businesses_list(request):
    category = request.GET.get('category', '')
    query = request.GET.get('q', '').strip()

    businesses = Business.objects.filter(is_active=True)

    if category:
        businesses = businesses.filter(category=category)
    if query:
        businesses = businesses.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )

    return render(request, 'businesses/list.html', {
        'businesses': businesses,
        'active_category': category,
        'query': query,
        'categories': Business.CATEGORY_CHOICES,
    })


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

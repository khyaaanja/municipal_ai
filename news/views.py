from django.shortcuts import render, get_object_or_404
from django.db.models import F
from .models import NewsArticle


def news_list(request):
    category = request.GET.get('category', '')
    articles = NewsArticle.objects.filter(is_active=True)
    if category:
        articles = articles.filter(category=category)
    pinned = articles.filter(is_pinned=True)
    regular = articles.filter(is_pinned=False)
    return render(request, 'news/list.html', {
        'articles': regular,
        'pinned': pinned,
        'active_category': category,
        'categories': NewsArticle.CATEGORY_CHOICES,
    })


def news_detail(request, slug):
    article = get_object_or_404(NewsArticle, slug=slug, is_active=True)
    NewsArticle.objects.filter(pk=article.pk).update(view_count=F('view_count') + 1)
    related = NewsArticle.objects.filter(
        category=article.category, is_active=True
    ).exclude(pk=article.pk)[:3]
    return render(request, 'news/detail.html', {'article': article, 'related': related})

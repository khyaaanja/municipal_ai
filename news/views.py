from django.shortcuts import render, get_object_or_404
from django.db.models import F
from django.core.paginator import Paginator
from django.core.cache import cache
from .models import NewsArticle


def news_list(request):
    category = request.GET.get('category', '')
    page_num = request.GET.get('page', '1')

    _cache_key = None
    if not request.user.is_authenticated and page_num == '1' and not category:
        _cache_key = 'news_list:page1'
        _cached = cache.get(_cache_key)
        if _cached:
            return _cached

    articles = NewsArticle.objects.filter(is_active=True)
    if category:
        articles = articles.filter(category=category)
    pinned = articles.filter(is_pinned=True)
    regular = articles.filter(is_pinned=False).order_by('-published_at')

    paginator = Paginator(regular, 10)
    page_obj = paginator.get_page(page_num)
    params = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    sidebar_articles = NewsArticle.objects.filter(is_active=True, is_pinned=False).order_by('-published_at')[:5]

    response = render(request, 'news/list.html', {
        'articles': page_obj,
        'page_obj': page_obj,
        'querystring': querystring,
        'pinned': pinned,
        'sidebar_articles': sidebar_articles,
        'active_category': category,
        'categories': NewsArticle.CATEGORY_CHOICES,
    })
    if _cache_key:
        cache.set(_cache_key, response, 120)  # 2 minutes — news is time-sensitive
    return response


def news_detail(request, slug):
    article = get_object_or_404(NewsArticle, slug=slug, is_active=True)
    NewsArticle.objects.filter(pk=article.pk).update(view_count=F('view_count') + 1)
    related = NewsArticle.objects.filter(
        category=article.category, is_active=True
    ).exclude(pk=article.pk)[:3]
    return render(request, 'news/detail.html', {'article': article, 'related': related})

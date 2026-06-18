import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from core.decorators import staff_required
from django.utils.text import slugify
from django.http import JsonResponse
from django.views.decorators.http import require_POST


# ── DASHBOARD ──────────────────────────────────────────────────────────────

@staff_required
def admin_dashboard(request):
    from accounts.models import User
    from tourism.models import Attraction
    from events.models import Event
    from businesses.models import Business
    from marketplace.models import Product, Order
    from news.models import NewsArticle
    from chatbot.models import KnowledgeBase

    return render(request, 'adminpanel/dashboard.html', {
        'user_count':       User.objects.count(),
        'attraction_count': Attraction.objects.count(),
        'event_count':      Event.objects.count(),
        'business_count':   Business.objects.count(),
        'product_count':    Product.objects.count(),
        'order_count':      Order.objects.count(),
        'news_count':       NewsArticle.objects.count(),
        'kb_count':         KnowledgeBase.objects.count(),
        'recent_orders':    Order.objects.select_related('user').order_by('-created_at')[:10],
    })


# ── HELPER ────────────────────────────────────────────────────────────────

def _unique_slug(model_cls, base_name, exclude_pk=None):
    slug = slugify(base_name)
    base = slug
    qs = model_cls.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    i = 1
    while qs.filter(slug=slug).exists():
        slug = f"{base}-{i}"
        i += 1
    return slug


# ── ATTRACTIONS ────────────────────────────────────────────────────────────

@staff_required
def cms_attractions(request):
    from tourism.models import Attraction
    items = Attraction.objects.select_related('category').order_by('-created_at')
    return render(request, 'adminpanel/attractions.html', {'items': items})


@staff_required
def cms_attraction_form(request, pk=None):
    from tourism.models import Attraction, AttractionCategory
    obj = get_object_or_404(Attraction, pk=pk) if pk else None
    categories = AttractionCategory.objects.all()

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Name is required.')
            return render(request, 'adminpanel/attraction_form.html', {'obj': obj, 'categories': categories})

        data = dict(
            name=name,
            slug=_unique_slug(Attraction, name, exclude_pk=pk),
            description=request.POST.get('description', ''),
            category_id=request.POST.get('category') or None,
            address=request.POST.get('address', ''),
            latitude=request.POST.get('latitude') or None,
            longitude=request.POST.get('longitude') or None,
            opening_hours=request.POST.get('opening_hours', ''),
            entry_fee=request.POST.get('entry_fee') or None,
            is_free='is_free' in request.POST,
            phone=request.POST.get('phone', ''),
            website=request.POST.get('website', ''),
            is_active='is_active' in request.POST,
            is_featured='is_featured' in request.POST,
        )
        if obj:
            for k, v in data.items():
                setattr(obj, k, v)
            obj.save()
            messages.success(request, f'"{name}" updated.')
        else:
            Attraction.objects.create(**data)
            messages.success(request, f'"{name}" added.')
        return redirect('adminpanel:cms_attractions')

    return render(request, 'adminpanel/attraction_form.html', {'obj': obj, 'categories': categories})


@staff_required
def cms_attraction_delete(request, pk):
    from tourism.models import Attraction
    obj = get_object_or_404(Attraction, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Attraction deleted.')
    return redirect('adminpanel:cms_attractions')


# ── EVENTS ────────────────────────────────────────────────────────────────

@staff_required
def cms_events(request):
    from events.models import Event
    items = Event.objects.order_by('-start_date')
    return render(request, 'adminpanel/events.html', {'items': items})


@staff_required
def cms_event_form(request, pk=None):
    from events.models import Event
    obj = get_object_or_404(Event, pk=pk) if pk else None

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Name is required.')
            return render(request, 'adminpanel/event_form.html', {'obj': obj, 'categories': Event.CATEGORY_CHOICES})

        data = dict(
            name=name,
            slug=_unique_slug(Event, name, exclude_pk=pk),
            description=request.POST.get('description', ''),
            category=request.POST.get('category', 'other'),
            venue=request.POST.get('venue', ''),
            address=request.POST.get('address', ''),
            start_date=request.POST.get('start_date'),
            end_date=request.POST.get('end_date') or None,
            organizer=request.POST.get('organizer', ''),
            entry_fee=request.POST.get('entry_fee') or None,
            is_free='is_free' in request.POST,
            max_attendees=request.POST.get('max_attendees') or None,
            is_active='is_active' in request.POST,
            is_featured='is_featured' in request.POST,
        )
        if obj:
            for k, v in data.items():
                setattr(obj, k, v)
            obj.save()
            messages.success(request, f'"{name}" updated.')
        else:
            Event.objects.create(**data)
            messages.success(request, f'"{name}" added.')
        return redirect('adminpanel:cms_events')

    return render(request, 'adminpanel/event_form.html', {'obj': obj, 'categories': Event.CATEGORY_CHOICES})


@staff_required
def cms_event_delete(request, pk):
    from events.models import Event
    obj = get_object_or_404(Event, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Event deleted.')
    return redirect('adminpanel:cms_events')


# ── BUSINESSES ────────────────────────────────────────────────────────────

@staff_required
def cms_businesses(request):
    from businesses.models import Business
    items = Business.objects.order_by('-created_at')
    return render(request, 'adminpanel/businesses.html', {'items': items})


@staff_required
def cms_business_form(request, pk=None):
    from businesses.models import Business
    obj = get_object_or_404(Business, pk=pk) if pk else None

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Name is required.')
            return render(request, 'adminpanel/business_form.html', {'obj': obj, 'categories': Business.CATEGORY_CHOICES})

        def _to_decimal(val, *, min_value=None, max_value=None):
            """Convert form values to a safe numeric string for DecimalField.
            Also normalize comma decimals ("85,123" -> "85.123") and validate range.
            """
            if val is None:
                return None
            val = str(val).strip()
            if val == "":
                return None

            # allow users to enter "85,123" style values
            val = val.replace(",", ".")

            try:
                f = float(val)
            except ValueError:
                return None

            if min_value is not None and f < min_value:
                return None
            if max_value is not None and f > max_value:
                return None

            # Keep as string so Django/DB can convert to DECIMAL properly
            return str(f)

        data = dict(
            name=name,
            slug=_unique_slug(Business, name, exclude_pk=pk),
            description=request.POST.get('description', ''),
            category=request.POST.get('category', 'other'),
            address=request.POST.get('address', ''),
            latitude=_to_decimal(request.POST.get('latitude'), min_value=-90, max_value=90),
            longitude=_to_decimal(request.POST.get('longitude'), min_value=-180, max_value=180),
            phone=request.POST.get('phone', ''),
            email=request.POST.get('email', ''),
            website=request.POST.get('website', ''),
            opening_hours=request.POST.get('opening_hours', ''),
            is_active='is_active' in request.POST,
            is_featured='is_featured' in request.POST,
            is_verified='is_verified' in request.POST,
        )
        if obj:
            for k, v in data.items():
                setattr(obj, k, v)
            obj.save()
            messages.success(request, f'"{name}" updated.')
        else:
            Business.objects.create(**data)
            messages.success(request, f'"{name}" added.')
        return redirect('adminpanel:cms_businesses')

    return render(request, 'adminpanel/business_form.html', {'obj': obj, 'categories': Business.CATEGORY_CHOICES})


@staff_required
def cms_business_delete(request, pk):
    from businesses.models import Business
    obj = get_object_or_404(Business, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Business deleted.')
    return redirect('adminpanel:cms_businesses')


# ── NEWS ──────────────────────────────────────────────────────────────────

@staff_required
def cms_news(request):
    from news.models import NewsArticle
    items = NewsArticle.objects.order_by('-published_at')
    return render(request, 'adminpanel/news.html', {'items': items})


@staff_required
def cms_news_form(request, pk=None):
    from news.models import NewsArticle
    obj = get_object_or_404(NewsArticle, pk=pk) if pk else None

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        if not title:
            messages.error(request, 'Title is required.')
            return render(request, 'adminpanel/news_form.html', {'obj': obj, 'categories': NewsArticle.CATEGORY_CHOICES})

        data = dict(
            title=title,
            slug=_unique_slug(NewsArticle, title, exclude_pk=pk),
            summary=request.POST.get('summary', ''),
            content=request.POST.get('content', ''),
            category=request.POST.get('category', 'general'),
            author=request.user,
            is_active='is_active' in request.POST,
            is_pinned='is_pinned' in request.POST,
        )
        if obj:
            for k, v in data.items():
                setattr(obj, k, v)
            obj.save()
            messages.success(request, f'"{title}" updated.')
        else:
            NewsArticle.objects.create(**data)
            messages.success(request, f'"{title}" published.')
        return redirect('adminpanel:cms_news')

    return render(request, 'adminpanel/news_form.html', {'obj': obj, 'categories': NewsArticle.CATEGORY_CHOICES})


@staff_required
def cms_news_delete(request, pk):
    from news.models import NewsArticle
    obj = get_object_or_404(NewsArticle, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Article deleted.')
    return redirect('adminpanel:cms_news')


# ── KNOWLEDGE BASE ────────────────────────────────────────────────────────

@staff_required
def cms_knowledge(request):
    from chatbot.models import KnowledgeBase
    items = KnowledgeBase.objects.order_by('-priority', 'title')
    return render(request, 'adminpanel/knowledge.html', {'items': items})


@staff_required
def cms_knowledge_form(request, pk=None):
    from chatbot.models import KnowledgeBase
    obj = get_object_or_404(KnowledgeBase, pk=pk) if pk else None

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        if not title:
            messages.error(request, 'Title is required.')
            return render(request, 'adminpanel/knowledge_form.html', {'obj': obj, 'categories': KnowledgeBase.CATEGORY_CHOICES})

        data = dict(
            title=title,
            content=request.POST.get('content', ''),
            category=request.POST.get('category', 'general'),
            keywords=request.POST.get('keywords', ''),
            priority=int(request.POST.get('priority', 0) or 0),
            is_active='is_active' in request.POST,
        )
        if obj:
            for k, v in data.items():
                setattr(obj, k, v)
            obj.save()
            messages.success(request, f'"{title}" updated.')
        else:
            KnowledgeBase.objects.create(**data)
            messages.success(request, f'"{title}" added.')
        return redirect('adminpanel:cms_knowledge')

    return render(request, 'adminpanel/knowledge_form.html', {'obj': obj, 'categories': KnowledgeBase.CATEGORY_CHOICES})


@staff_required
def cms_knowledge_delete(request, pk):
    from chatbot.models import KnowledgeBase
    obj = get_object_or_404(KnowledgeBase, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Entry deleted.')
    return redirect('adminpanel:cms_knowledge')


# ── MARKETPLACE: PRODUCTS ─────────────────────────────────────────────────

@staff_required
def cms_products(request):
    from marketplace.models import Product
    items = Product.objects.select_related('category', 'vendor').order_by('-created_at')
    return render(request, 'adminpanel/products.html', {'items': items})


@staff_required
def cms_product_form(request, pk=None):
    from marketplace.models import Product, ProductCategory, VendorProfile
    obj = get_object_or_404(Product, pk=pk) if pk else None
    categories = ProductCategory.objects.all()
    vendors = VendorProfile.objects.filter(is_approved=True).select_related('user')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Name is required.')
            return render(request, 'adminpanel/product_form.html', {
                'obj': obj, 'categories': categories, 'vendors': vendors
            })

        vendor_id = request.POST.get('vendor')
        if not vendor_id:
            messages.error(request, 'Vendor is required.')
            return render(request, 'adminpanel/product_form.html', {
                'obj': obj, 'categories': categories, 'vendors': vendors
            })

        data = dict(
            name=name,
            slug=_unique_slug(Product, name, exclude_pk=pk),
            description=request.POST.get('description', ''),
            category_id=request.POST.get('category') or None,
            vendor_id=vendor_id,
            price=request.POST.get('price') or 0,
            original_price=request.POST.get('original_price') or None,
            stock=int(request.POST.get('stock', 0) or 0),
            is_active='is_active' in request.POST,
            is_featured='is_featured' in request.POST,
        )
        if obj:
            for k, v in data.items():
                setattr(obj, k, v)
            obj.save()
            messages.success(request, f'"{name}" updated.')
        else:
            Product.objects.create(**data)
            messages.success(request, f'"{name}" added.')
        return redirect('adminpanel:cms_products')

    return render(request, 'adminpanel/product_form.html', {
        'obj': obj, 'categories': categories, 'vendors': vendors
    })


@staff_required
def cms_product_delete(request, pk):
    from marketplace.models import Product
    obj = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Product deleted.')
    return redirect('adminpanel:cms_products')


# ── MARKETPLACE: PRODUCT CATEGORIES ──────────────────────────────────────

@staff_required
def cms_product_categories(request):
    from marketplace.models import ProductCategory
    items = ProductCategory.objects.annotate_product_count = None  # just list
    items = ProductCategory.objects.all().order_by('name')
    return render(request, 'adminpanel/product_categories.html', {'items': items})


@staff_required
def cms_product_category_form(request, pk=None):
    from marketplace.models import ProductCategory
    obj = get_object_or_404(ProductCategory, pk=pk) if pk else None

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Name is required.')
            return render(request, 'adminpanel/product_category_form.html', {'obj': obj})

        slug = _unique_slug(ProductCategory, name, exclude_pk=pk)
        icon = request.POST.get('icon', '').strip()

        if obj:
            obj.name = name
            obj.slug = slug
            obj.icon = icon
            obj.save()
            messages.success(request, f'"{name}" updated.')
        else:
            ProductCategory.objects.create(name=name, slug=slug, icon=icon)
            messages.success(request, f'"{name}" added.')
        return redirect('adminpanel:cms_product_categories')

    return render(request, 'adminpanel/product_category_form.html', {'obj': obj})


@staff_required
def cms_product_category_delete(request, pk):
    from marketplace.models import ProductCategory
    obj = get_object_or_404(ProductCategory, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Category deleted.')
    return redirect('adminpanel:cms_product_categories')


# ── MARKETPLACE: VENDORS ──────────────────────────────────────────────────

@staff_required
def cms_vendors(request):
    from marketplace.models import VendorProfile
    items = VendorProfile.objects.select_related('user').order_by('-created_at')
    return render(request, 'adminpanel/vendors.html', {'items': items})


@staff_required
def cms_vendor_toggle(request, pk):
    from marketplace.models import VendorProfile
    vendor = get_object_or_404(VendorProfile, pk=pk)
    if request.method == 'POST':
        vendor.is_approved = not vendor.is_approved
        vendor.save()
        status = 'approved' if vendor.is_approved else 'suspended'
        messages.success(request, f'{vendor.shop_name} has been {status}.')
    return redirect('adminpanel:cms_vendors')


# ── MARKETPLACE: ORDERS ───────────────────────────────────────────────────

@staff_required
def cms_orders(request):
    from marketplace.models import Order
    status_filter = request.GET.get('status', '')
    orders = Order.objects.select_related('user').prefetch_related('items__product').order_by('-created_at')
    if status_filter:
        orders = orders.filter(status=status_filter)
    return render(request, 'adminpanel/orders.html', {
        'orders': orders,
        'status_filter': status_filter,
        'status_choices': Order.STATUS_CHOICES,
    })


@staff_required
def cms_order_status(request, pk):
    from marketplace.models import Order
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        valid = [s[0] for s in Order.STATUS_CHOICES]
        if new_status in valid:
            order.status = new_status
            order.save()
            messages.success(request, f'Order #{order.pk} marked as {new_status}.')
        else:
            messages.error(request, 'Invalid status.')
    return redirect('adminpanel:cms_orders')


# ── MAP CMS ───────────────────────────────────────────────────────────────

@staff_required
def cms_map(request):
    from tourism.models import Attraction
    from businesses.models import Business
    from events.models import Event
    from django.conf import settings

    def _serialize(obj, model_type, name, slug, lat, lng, category=''):
        return {
            'pk':       obj.pk,
            'model':    model_type,
            'name':     name,
            'slug':     slug,
            'category': category,
            'lat':      float(lat) if lat else None,
            'lng':      float(lng) if lng else None,
            'pinned':   lat is not None and lng is not None,
        }

    items = []

    for a in Attraction.objects.select_related('category').order_by('name'):
        items.append(_serialize(
            a, 'attraction', a.name, a.slug,
            a.latitude, a.longitude,
            a.category.name if a.category else 'Attraction',
        ))

    for b in Business.objects.order_by('name'):
        items.append(_serialize(
            b, 'business', b.name, b.slug,
            b.latitude, b.longitude,
            b.get_category_display(),
        ))

    for e in Event.objects.order_by('name'):
        items.append(_serialize(
            e, 'event', e.name, e.slug,
            e.latitude, e.longitude,
            e.get_category_display(),
        ))

    pinned   = [i for i in items if i['pinned']]
    unpinned = [i for i in items if not i['pinned']]

    return render(request, 'adminpanel/map.html', {
        'items_json':    json.dumps(items),
        'pinned_count':  len(pinned),
        'unpinned_count': len(unpinned),
        'city_lat':      settings.CITY_LAT,
        'city_lng':      settings.CITY_LNG,
        'city_name':     settings.CITY_NAME,
    })


@staff_required
@require_POST
def cms_map_update_location(request):
    try:
        data  = json.loads(request.body)
        model = data['model']
        pk    = int(data['pk'])
        lat   = float(data['lat'])
        lng   = float(data['lng'])
    except (KeyError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Invalid payload'}, status=400)

    MODEL_MAP = {
        'attraction': ('tourism.models', 'Attraction'),
        'business':   ('businesses.models', 'Business'),
        'event':      ('events.models', 'Event'),
    }

    if model not in MODEL_MAP:
        return JsonResponse({'success': False, 'error': 'Unknown model'}, status=400)

    module_path, class_name = MODEL_MAP[model]
    import importlib
    module = importlib.import_module(module_path)
    ModelCls = getattr(module, class_name)

    try:
        obj = ModelCls.objects.get(pk=pk)
    except ModelCls.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Not found'}, status=404)

    obj.latitude  = lat
    obj.longitude = lng
    obj.save(update_fields=['latitude', 'longitude'])

    return JsonResponse({'success': True, 'name': str(obj), 'lat': lat, 'lng': lng})


@staff_required
@require_POST
def cms_map_clear_location(request):
    try:
        data  = json.loads(request.body)
        model = data['model']
        pk    = int(data['pk'])
    except (KeyError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Invalid payload'}, status=400)

    MODEL_MAP = {
        'attraction': ('tourism.models', 'Attraction'),
        'business':   ('businesses.models', 'Business'),
        'event':      ('events.models', 'Event'),
    }
    if model not in MODEL_MAP:
        return JsonResponse({'success': False, 'error': 'Unknown model'}, status=400)

    module_path, class_name = MODEL_MAP[model]
    import importlib
    module = importlib.import_module(module_path)
    ModelCls = getattr(module, class_name)

    try:
        obj = ModelCls.objects.get(pk=pk)
    except ModelCls.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Not found'}, status=404)

    obj.latitude  = None
    obj.longitude = None
    obj.save(update_fields=['latitude', 'longitude'])

    return JsonResponse({'success': True})

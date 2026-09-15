import base64
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.cache import cache

_HOMEPAGE_CACHE_KEY = 'homepage_context'
_HOMEPAGE_TTL = 900  # 15 minutes — reduces cache rebuild frequency by 3x


def build_homepage_context():
    """Build homepage context data — reusable from view or Celery task."""
    from tourism.models import Attraction
    from events.models import Event
    from businesses.models import Business
    from marketplace.models import Product
    from news.models import NewsArticle
    from django.utils import timezone

    today = timezone.now().date()
    now = timezone.now()
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Real complaint stats
    try:
        from complaints.models import Complaint
        total_complaints  = Complaint.objects.count()
        resolved_month    = Complaint.objects.filter(
            status='RESOLVED', updated_at__gte=this_month_start
        ).count()
        pending_complaints = Complaint.objects.filter(status='PENDING').count()
    except Exception:
        total_complaints = resolved_month = pending_complaints = 0

    # Announcements from new model
    try:
        from core.models import Announcement, WardProject
        latest_announcements = list(
            Announcement.objects.filter(is_active=True, ward_number__isnull=True)
            .select_related('posted_by').order_by('-created_at')[:3]
        )
        active_projects = WardProject.objects.filter(
            status='IN_PROGRESS'
        ).count()
    except Exception:
        latest_announcements = []
        active_projects = 0

    # Resolution rate
    resolution_rate = round(resolved_month / max(total_complaints, 1) * 100)

    return {
        'featured_attractions': list(Attraction.objects.filter(is_active=True, is_featured=True).select_related('category').prefetch_related('images')[:6]),
        'today_events': list(Event.objects.filter(is_active=True, start_date__date=today)[:4]),
        'upcoming_events': list(Event.objects.filter(is_active=True, start_date__gte=now).order_by('start_date')[:4]),
        'popular_businesses': list(Business.objects.filter(is_active=True, is_featured=True).select_related('owner')[:6]),
        'featured_products': list(Product.objects.filter(is_active=True).select_related('category', 'vendor').prefetch_related('images')[:8]),
        'latest_news': list(NewsArticle.objects.filter(is_active=True)[:4]),
        'stat_complaints_total':   total_complaints,
        'stat_resolved_month':     resolved_month,
        'stat_pending':            pending_complaints,
        'latest_announcements':    latest_announcements,
        'active_projects':         active_projects,
        'resolution_rate':         resolution_rate,
    }


@ensure_csrf_cookie
def homepage(request):
    ctx = cache.get(_HOMEPAGE_CACHE_KEY)
    if ctx is None:
        ctx = build_homepage_context()
        cache.set(_HOMEPAGE_CACHE_KEY, ctx, _HOMEPAGE_TTL)

    # Ward activity feed — not cached, user/ward-specific
    ward_activity = []
    if request.user.is_authenticated and request.user.ward_number:
        try:
            from complaints.models import Complaint as _C
            ward_activity = list(
                _C.objects.filter(ward_number=request.user.ward_number)
                .order_by('-updated_at')[:5]
            )
        except Exception:
            pass

    return render(request, 'core/homepage.html', {**ctx, 'ward_activity': ward_activity})


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


def map_pins_api(request):
    """Return JSON with all mappable attractions and businesses."""
    from django.http import JsonResponse
    from tourism.models import Attraction
    from businesses.models import Business

    pins = []

    # Attractions
    try:
        for a in Attraction.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False).select_related('category'):
            pins.append({
                'type': 'attraction',
                'id': a.id,
                'name': a.name,
                'lat': float(a.latitude),
                'lng': float(a.longitude),
                'category': a.category.name if a.category else 'Heritage',
                'description': a.description[:150] if a.description else '',
                'address': a.address or '',
                'entry_fee': f"NPR {a.entry_fee}" if a.entry_fee else 'Free',
                'url': f'/attractions/{a.pk}/',
            })
    except Exception:
        pass

    # Businesses
    try:
        for b in Business.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False):
            pins.append({
                'type': 'business',
                'id': b.id,
                'name': b.name,
                'lat': float(b.latitude),
                'lng': float(b.longitude),
                'category': b.category or 'Business',
                'description': '',
                'address': b.address or '',
                'rating': round(float(b.avg_rating), 1) if b.avg_rating else None,
                'url': f'/businesses/{b.pk}/',
            })
    except Exception:
        pass

    return JsonResponse({'pins': pins})


from django.views.decorators.http import require_http_methods
from django.conf import settings
from core.utils import (
    MAX_AI_IMAGE_BYTES, compress_image_base64, decode_image_base64,
    get_client_ip, image_hash,
)


@require_http_methods(["POST"])
def scan_api(request):
    """
    Vision scanner: accepts a base64 JPEG/PNG from the camera,
    sends it to Groq's vision model, returns a cultural AI description.
    Uses image compression and caching to reduce API cost.
    """
    ip = get_client_ip(request)
    rate_key = f'scan_api_{ip}'
    try:
        count = cache.incr(rate_key)
    except ValueError:
        cache.set(rate_key, 1, 3600)
        count = 1
    if count > 30:
        return JsonResponse({'error': 'Rate limit — too many scans. Try again later.'}, status=429)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    image_data = data.get('image', '')
    user_question = data.get('question', '')
    if not isinstance(image_data, str) or not isinstance(user_question, str):
        return JsonResponse({'error': 'Image and question must be strings'}, status=400)
    user_question = user_question.strip()[:300]

    if not image_data:
        return JsonResponse({'error': 'No image provided'}, status=400)

    if ',' in image_data:
        image_data = image_data.split(',', 1)[1]

    raw_image = decode_image_base64(image_data, max_bytes=MAX_AI_IMAGE_BYTES)
    if raw_image is None or len(raw_image) < 500:
        return JsonResponse({'error': 'Image too small or corrupt'}, status=400)
    image_data = base64.b64encode(raw_image).decode('ascii')

    # Compress image to reduce token cost ~60%
    image_data = compress_image_base64(image_data, max_width=640)

    if len(image_data) < 500:
        return JsonResponse({'error': 'Image too small or corrupt after processing'}, status=400)

    # Check cache for identical scan
    img_hash = image_hash(image_data)
    cache_key = f'scan_result_{img_hash}_{hash(user_question)}'
    cached_result = cache.get(cache_key)
    if cached_result:
        return JsonResponse({'success': True, 'description': cached_result, 'cached': True})

    api_key = getattr(settings, 'GROQ_API_KEY', '')
    if not api_key:
        return JsonResponse({'error': 'AI service not configured'}, status=503)

    try:
        from chatbot.ai_engine import _get_groq_client
        from django.utils import timezone as _tz
        client = _get_groq_client(api_key)
        city    = getattr(settings, 'CITY_NAME', 'Bhaktapur')
        country = getattr(settings, 'CITY_COUNTRY', 'Nepal')
        model   = getattr(settings, 'GROQ_VISION_MODEL', 'meta-llama/llama-4-scout-17b-16e-instruct')
        fallback_model = getattr(settings, 'GROQ_FALLBACK_MODEL', 'llama-3.2-11b-vision-preview')
        today = _tz.now().strftime('%A, %B %d, %Y')

        user_prompt = (
            f"You are an expert AI cultural guide for {city}, {country} — a UNESCO World Heritage city.\n"
            f"Today: {today} | Currency: Nepalese Rupee (NPR)\n\n"
            f"Look at this image and identify what is shown:\n"
            f"• **Temple / monument / heritage site** → name it, history, deity/purpose, entry fee, opening hours, visitor tips\n"
            f"• **Food or dish** → name it, taste, key ingredients, where to find it in {city}, approximate price in NPR\n"
            f"• **Craft or artwork** → craft tradition, materials, cultural value, where to buy, price range\n"
            f"• **Person in traditional attire** → occasion, what the dress signifies, cultural context\n"
            f"• **Street, square, or building** → name it, what to experience there, nearby attractions\n"
            f"• **Anything else** → identify it and connect it to {city} culture or tourism\n\n"
            "Start with a **bold title** (e.g. **Nyatapola Temple**). "
            "Then provide 3-4 sentences of rich, accurate, engaging information. "
            "Include at least one practical visitor tip. Be warm and proud of the cultural heritage."
            + (f"\n\nThe visitor specifically asks: {user_question}" if user_question else "")
        )

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'image_url',
                                'image_url': {'url': f'data:image/jpeg;base64,{image_data}'},
                            },
                            {'type': 'text', 'text': user_prompt},
                        ],
                    }
                ],
                max_tokens=600,
                temperature=0.4,
                timeout=30,
            )
        except Exception:
            try:
                response = client.chat.completions.create(
                    model=fallback_model,
                    messages=[
                        {
                            'role': 'user',
                            'content': [
                                {
                                    'type': 'image_url',
                                    'image_url': {'url': f'data:image/jpeg;base64,{image_data}'},
                                },
                                {'type': 'text', 'text': user_prompt},
                            ],
                        }
                    ],
                    max_tokens=500,
                    temperature=0.4,
                    timeout=30,
                )
            except Exception as fb_err:
                if '429' in str(fb_err):
                    return JsonResponse({
                        'error': 'AI service is currently overloaded. Please wait a moment and try again.',
                        'retry_after': 30,
                    }, status=429)
                raise

        description = response.choices[0].message.content or ''
        if not description.strip():
            description = 'Could not identify. Please try with a clearer, well-lit photo.'

        cache.set(cache_key, description, 3600)

        return JsonResponse({'success': True, 'description': description})

    except Exception as e:
        error_msg = str(e)
        if '429' in error_msg:
            return JsonResponse({
                'error': 'AI service is currently overloaded. Please wait a moment and try again.',
                'retry_after': 30,
            }, status=429)
        if getattr(settings, 'DEBUG', False):
            return JsonResponse({'error': error_msg}, status=500)
        return JsonResponse(
            {'error': 'Could not analyze image. Ensure the image is clear and try again.'},
            status=500,
        )


@login_required
def orders_view(request):
    from marketplace.models import Order
    orders = Order.objects.filter(user=request.user).prefetch_related('items__product').order_by('-created_at')
    return render(request, 'core/orders.html', {'orders': orders})


def handler404(request, exception=None):
    from django.shortcuts import render as _render
    return _render(request, '404.html', status=404)


def handler500(request):
    from django.shortcuts import render as _render
    return _render(request, '500.html', status=500)


def google_oauth_error(request):
    # social-auth forwards the reason in query params.
    # Common keys include: error, message, error_description.
    msg = (
        request.GET.get('error')
        or request.GET.get('message')
        or request.GET.get('error_description')
        or ''
    )
    # Try social-auth's standard error context too.
    if not msg:
        msg = request.session.get('social_auth_error_message', '')

    return render(request, 'auth_error.html', {
        'message': msg,
    })



def transparency_dashboard(request):
    from complaints.models import Complaint
    from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField
    import json as _json
    from datetime import timedelta
    from django.utils import timezone

    _CACHE_KEY = 'transparency_ctx'
    ctx = cache.get(_CACHE_KEY)
    if ctx is None:
        now = timezone.now()
        total     = Complaint.objects.count()
        resolved  = Complaint.objects.filter(status='RESOLVED').count()
        rate      = round(resolved / total * 100) if total else 0

        # Average resolution time in days
        avg_days = 0
        try:
            resolved_qs = Complaint.objects.filter(status='RESOLVED', resolved_at__isnull=False)
            if resolved_qs.exists():
                deltas = [(c.resolved_at - c.created_at).days for c in resolved_qs[:200]]
                avg_days = round(sum(deltas) / len(deltas), 1)
        except Exception:
            pass

        # By category
        cat_label = dict(Complaint.CATEGORY_CHOICES)
        by_cat = list(Complaint.objects.values('category').annotate(n=Count('id')).order_by('-n'))
        cat_labels = [cat_label.get(r['category'], r['category']) for r in by_cat]
        cat_values = [r['n'] for r in by_cat]

        # Monthly filed vs resolved (last 6 months)
        months_labels, filed_vals, resolved_vals = [], [], []
        for i in range(5, -1, -1):
            d = now - timedelta(days=30 * i)
            start = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end   = (start + timedelta(days=32)).replace(day=1)
            months_labels.append(d.strftime('%b %Y'))
            filed_vals.append(Complaint.objects.filter(created_at__gte=start, created_at__lt=end).count())
            resolved_vals.append(Complaint.objects.filter(status='RESOLVED', resolved_at__gte=start, resolved_at__lt=end).count())

        # Top-voted complaints
        top_voted = list(
            Complaint.objects.annotate(vote_count=Count('votes'))
            .filter(vote_count__gt=0)
            .order_by('-vote_count')[:5]
        )

        # Map pins for geo-located complaints
        STATUS_COLOUR = {
            'PENDING': '#C9A227', 'IN_REVIEW': '#4A7AB5',
            'IN_PROGRESS': '#D4620A', 'RESOLVED': '#4ade80', 'REJECTED': '#C13B2A',
        }
        complaint_pins = [
            {
                'lat': c.latitude, 'lng': c.longitude,
                'id': c.complaint_id, 'title': c.title[:60],
                'status': c.status, 'colour': STATUS_COLOUR.get(c.status, '#C9A227'),
            }
            for c in Complaint.objects.filter(
                latitude__isnull=False, longitude__isnull=False
            ).only('complaint_id', 'title', 'status', 'latitude', 'longitude')[:300]
        ]

        # Civic leaderboard — top 10 citizens by civic score (single annotated query)
        from accounts.models import User
        from django.db.models import Count as _Count, Q as _Q
        annotated = (
            User.objects.filter(role='citizen')
            .annotate(
                filed=_Count('complaints', distinct=True),
                resolved=_Count('complaints', filter=_Q(complaints__status='RESOLVED'), distinct=True),
                votes=_Count('complaintvote', distinct=True),
            )
        )
        leaderboard = []
        for u in annotated:
            score = u.filed * 10 + u.resolved * 50 + u.votes * 2
            if score > 0:
                leaderboard.append({'user': u, 'score': score, 'filed': u.filed, 'resolved': u.resolved})
        leaderboard.sort(key=lambda x: -x['score'])
        leaderboard = leaderboard[:10]

        # SLA compliance — what % of resolved complaints were resolved within SLA window
        SLA_DAYS = {'CRITICAL': 1, 'HIGH': 3, 'MEDIUM': 7, 'LOW': 14}

        # Use a single aggregated query instead of Python loop over 500 records × 4 priorities
        resolved_qs = Complaint.objects.filter(status='RESOLVED', resolved_at__isnull=False)
        sla_counts_raw = (
            resolved_qs.values('priority')
            .annotate(
                total=Count('id'),
            )
        )
        sla_counts = {r['priority']: r['total'] for r in sla_counts_raw}

        # For within-sla counts, compute per-priority using the database
        from django.db.models import Case as DBCase, When, Value, IntegerField
        sla_within_raw = {}
        for priority, days in SLA_DAYS.items():
            count_within = resolved_qs.filter(
                priority=priority,
                resolved_at__lte=timezone.now(),  # resolved_at already filtered
            ).extra(
                where=["DATEDIFF(resolved_at, created_at) <= %s"],
                params=[days],
            ).count()
            sla_within_raw[priority] = count_within

        sla_rows = []
        sla_total_within = 0
        sla_total_resolved = 0
        for priority, days in SLA_DAYS.items():
            count_resolved = sla_counts.get(priority, 0)
            count_within = sla_within_raw.get(priority, 0)
            compliance_pct = round(count_within / count_resolved * 100) if count_resolved else None
            overdue_count = Complaint.objects.filter(
                priority=priority,
                created_at__lt=now - timedelta(days=days),
            ).exclude(status__in=('RESOLVED', 'REJECTED')).count()
            sla_rows.append({
                'priority': priority,
                'sla_days': days,
                'resolved': count_resolved,
                'within_sla': count_within,
                'compliance_pct': compliance_pct,
                'overdue': overdue_count,
            })
            sla_total_within += count_within
            sla_total_resolved += count_resolved
        overall_sla_pct = round(sla_total_within / sla_total_resolved * 100) if sla_total_resolved else None

        ctx = {
            'total': total, 'resolved': resolved, 'rate': rate, 'avg_days': avg_days,
            'cat_labels_json':    _json.dumps(cat_labels),
            'cat_values_json':    _json.dumps(cat_values),
            'months_labels_json': _json.dumps(months_labels),
            'filed_json':         _json.dumps(filed_vals),
            'resolved_json':      _json.dumps(resolved_vals),
            'top_voted':          top_voted,
            'complaint_pins_json': _json.dumps(complaint_pins),
            'has_pins':           bool(complaint_pins),
            'leaderboard':        leaderboard,
            'sla_rows':           sla_rows,
            'overall_sla_pct':    overall_sla_pct,
        }
        cache.set(_CACHE_KEY, ctx, 3600)
    return render(request, 'core/transparency.html', ctx)


def ward_projects_public(request):
    """Public view of ward projects — citizens can see live progress."""
    from core.models import WardProject
    ward_f = request.GET.get('ward', '')
    qs = WardProject.objects.all()
    if ward_f:
        try:
            qs = qs.filter(ward_number=int(ward_f))
        except ValueError:
            pass
    projects = qs.order_by('ward_number', '-created_at')
    in_progress = qs.filter(status='IN_PROGRESS').count()
    completed   = qs.filter(status='COMPLETED').count()
    return render(request, 'core/ward_projects.html', {
        'projects':    projects,
        'ward_f':      ward_f,
        'wards':       range(1, 18),
        'in_progress': in_progress,
        'completed':   completed,
        'total':       qs.count(),
        'status_choices': WardProject.STATUS_CHOICES,
    })


def announcements_public(request):
    """Public announcements — city-wide and per-ward."""
    from core.models import Announcement
    ward_f = request.GET.get('ward', '')
    qs = Announcement.objects.filter(is_active=True)
    if ward_f:
        try:
            w = int(ward_f)
            qs = qs.filter(Q(ward_number=w) | Q(ward_number__isnull=True))
        except ValueError:
            pass
    announcements = qs.select_related('posted_by').prefetch_related('comments__user').order_by('-created_at')[:50]
    return render(request, 'core/announcements.html', {
        'announcements': announcements,
        'ward_f': ward_f,
        'wards': range(1, 18),
    })


@login_required
def citizen_dashboard(request):
    """Personalised hub for logged-in citizens."""
    from complaints.models import Complaint, ComplaintFollow, ComplaintVote, ComplaintSupport, ComplaintEscalation
    from accounts.models import Notification
    from core.models import Announcement

    user = request.user

    # Their complaints — last 5 with status
    my_complaints = Complaint.objects.filter(user=user).order_by('-updated_at')[:5]
    total_filed    = Complaint.objects.filter(user=user).count()
    total_resolved = Complaint.objects.filter(user=user, status='RESOLVED').count()
    open_count     = Complaint.objects.filter(user=user, status__in=('PENDING','IN_REVIEW','IN_PROGRESS')).count()

    # Followed complaints with status
    followed = list(
        ComplaintFollow.objects.filter(user=user)
        .select_related('complaint')
        .order_by('-created_at')[:5]
    )

    # Unread notifications
    unread_notifications = list(
        Notification.objects.filter(user=user, is_read=False)
        .order_by('-created_at')[:5]
    )
    unread_count = Notification.objects.filter(user=user, is_read=False).count()

    # Ward feed + enhanced stats
    ward_feed = []
    ward_announcements = []
    ward_total = ward_resolved = ward_in_progress = ward_active_projects = 0
    ward_latest_announcement = None

    if user.ward_number:
        from core.models import WardProject
        ward_qs = Complaint.objects.filter(ward_number=user.ward_number)
        ward_total       = ward_qs.count()
        ward_resolved    = ward_qs.filter(status='RESOLVED').count()
        ward_in_progress = ward_qs.filter(status='IN_PROGRESS').count()
        ward_feed = list(ward_qs.order_by('-updated_at')[:5])

        ward_active_projects = WardProject.objects.filter(
            ward_number=user.ward_number, status='IN_PROGRESS'
        ).count()

        ward_announcements = list(
            Announcement.objects.filter(is_active=True)
            .filter(Q(ward_number=user.ward_number) | Q(ward_number__isnull=True))
            .order_by('-created_at')[:3]
        )
        if ward_announcements:
            ward_latest_announcement = ward_announcements[0]
    else:
        ward_announcements = list(
            Announcement.objects.filter(is_active=True, ward_number__isnull=True)
            .order_by('-created_at')[:3]
        )

    # Cumulative civic impact (sum of resolved complaint impact estimates)
    from complaints.views import _calc_impact
    resolved_complaints = Complaint.objects.filter(user=user, status='RESOLVED')
    total_impact = sum(_calc_impact(c) for c in resolved_complaints)

    # Co-signed complaints (I'm Affected Too)
    supported = list(
        ComplaintSupport.objects.filter(user=user)
        .select_related('complaint')
        .order_by('-supported_at')[:5]
    )
    supported_count = ComplaintSupport.objects.filter(user=user).count()

    # Pending escalations the user filed
    my_escalations = list(
        ComplaintEscalation.objects.filter(escalated_by=user, is_reviewed=False)
        .select_related('complaint')
        .order_by('-escalated_at')[:3]
    )

    # Civic participation data
    my_proposals = []
    my_proposal_count = 0
    active_polls = []
    voted_poll_ids = set()
    my_sr = []
    pending_sr_count = 0
    open_petitions = []
    signed_petition_ids = set()
    poll_votes_count = 0
    petition_signed_count = 0
    try:
        from civic.models import Proposal, Petition, PetitionSignature, PollVote as _PV, CivicPoll
        from services.models import ServiceRequest as _SR
        my_proposals = list(Proposal.objects.filter(submitted_by=user).order_by('-created_at')[:3])
        my_proposal_count = Proposal.objects.filter(submitted_by=user).count()
        active_polls = list(CivicPoll.objects.filter(status='ACTIVE').filter(
            Q(ward_number=user.ward_number) | Q(ward_number__isnull=True))[:3])
        voted_poll_ids = set(_PV.objects.filter(user=user).values_list('poll_id', flat=True))
        my_sr = list(_SR.objects.filter(applicant=user).order_by('-created_at')[:3])
        pending_sr_count = _SR.objects.filter(
            applicant=user,
            status__in=('SUBMITTED', 'DOCUMENTS', 'IN_REVIEW', 'APPROVED', 'READY')
        ).count()
        open_petitions = list(Petition.objects.filter(status='OPEN').filter(
            Q(ward_number=user.ward_number) | Q(ward_number__isnull=True)
        ).order_by('-signature_count')[:3])
        signed_petition_ids = set(PetitionSignature.objects.filter(
            user=user).values_list('petition_id', flat=True))
        poll_votes_count = _PV.objects.filter(user=user).count()
        petition_signed_count = PetitionSignature.objects.filter(user=user).count()
    except Exception:
        pass

    # Civic score — co-signing now counts (5 pts per support)
    votes_cast = ComplaintVote.objects.filter(user=user).count()
    civic_score = (
        total_filed * 10 + total_resolved * 50 + votes_cast * 2 + supported_count * 5
        + my_proposal_count * 15
        + petition_signed_count * 3
        + poll_votes_count * 2
    )
    if civic_score >= 500:
        badge, badge_color, next_badge, pts_needed = 'Platinum Champion', '#4A7AB5', None, 0
    elif civic_score >= 200:
        badge, badge_color, next_badge, pts_needed = 'Gold Civic Leader', '#C9A227', 'Platinum', 500 - civic_score
    elif civic_score >= 80:
        badge, badge_color, next_badge, pts_needed = 'Silver Activist', '#888', 'Gold', 200 - civic_score
    elif civic_score >= 20:
        badge, badge_color, next_badge, pts_needed = 'Bronze Citizen', '#CD7F32', 'Silver', 80 - civic_score
    else:
        badge, badge_color, next_badge, pts_needed = 'New Citizen', '#aaa', 'Bronze', 20 - civic_score

    return render(request, 'core/citizen_dashboard.html', {
        'my_complaints':       my_complaints,
        'total_filed':         total_filed,
        'total_resolved':      total_resolved,
        'open_count':          open_count,
        'followed':            followed,
        'unread_notifications': unread_notifications,
        'unread_count':        unread_count,
        'ward_feed':           ward_feed,
        'ward_announcements':  ward_announcements,
        'ward_total':          ward_total,
        'ward_resolved':       ward_resolved,
        'ward_in_progress':    ward_in_progress,
        'ward_active_projects': ward_active_projects,
        'ward_latest_announcement': ward_latest_announcement,
        'civic_score':         civic_score,
        'badge':               badge,
        'badge_color':         badge_color,
        'next_badge':          next_badge,
        'pts_needed':          pts_needed,
        'votes_cast':          votes_cast,
        'supported':           supported,
        'supported_count':     supported_count,
        'my_escalations':      my_escalations,
        'total_impact':        total_impact,
        'my_proposals':        my_proposals,
        'my_proposal_count':   my_proposal_count,
        'active_polls':        active_polls,
        'voted_poll_ids':      voted_poll_ids,
        'my_sr':               my_sr,
        'pending_sr_count':    pending_sr_count,
        'open_petitions':      open_petitions,
        'signed_petition_ids': signed_petition_ids,
        'poll_votes_count':    poll_votes_count,
        'petition_signed_count': petition_signed_count,
    })


def ward_pulse(request, ward_number):
    """Per-ward citizen hub — complaint stats, projects, budget, announcements."""
    from complaints.models import Complaint
    from core.models import WardProject, WardBudget, Announcement, WardProjectFollow, AnnouncementComment
    from django.db.models import Count, Avg
    from accounts.models import User

    if ward_number < 1 or ward_number > 17:
        from django.http import Http404
        raise Http404

    # Complaint stats
    ward_qs = Complaint.objects.filter(ward_number=ward_number)
    total_complaints  = ward_qs.count()
    resolved_count    = ward_qs.filter(status='RESOLVED').count()
    in_progress_count = ward_qs.filter(status='IN_PROGRESS').count()
    pending_count     = ward_qs.filter(status='PENDING').count()
    resolution_rate   = round(resolved_count / total_complaints * 100) if total_complaints else 0

    # Category breakdown
    cat_label = dict(Complaint.CATEGORY_CHOICES)
    top_categories = [
        {'label': cat_label.get(r['category'], r['category']), 'n': r['n']}
        for r in ward_qs.values('category').annotate(n=Count('id')).order_by('-n')[:5]
    ]

    # Top-voted open complaints
    top_issues = list(
        ward_qs.exclude(status__in=('RESOLVED', 'REJECTED'))
        .annotate(vote_count=Count('votes'))
        .order_by('-vote_count')[:5]
    )

    # Projects
    projects = list(WardProject.objects.filter(ward_number=ward_number).order_by('-updated_at'))
    active_project_count = sum(1 for p in projects if p.status == 'IN_PROGRESS')

    # Budget
    budget = WardBudget.objects.filter(ward_number=ward_number).order_by('-fiscal_year').first()

    # Announcements
    announcements = list(
        Announcement.objects.filter(is_active=True)
        .filter(Q(ward_number=ward_number) | Q(ward_number__isnull=True))
        .select_related('posted_by')
        .prefetch_related('comments__user')
        .order_by('-created_at')[:8]
    )

    # Chairperson for this ward
    chairperson = User.objects.filter(role='chairperson', ward_number=ward_number).first()

    # Citizen satisfaction (avg service rating for resolved complaints in ward)
    from complaints.models import ServiceRating
    avg_rating = ServiceRating.objects.filter(
        complaint__ward_number=ward_number
    ).aggregate(avg=Avg('rating'))['avg']
    avg_rating = round(avg_rating, 1) if avg_rating else None

    # Civic participation data for this ward
    upcoming_meeting = None
    open_proposals_count = 0
    ward_active_polls = []
    ward_open_petitions = []
    try:
        from civic.models import Proposal as _Prop, WardMeeting as _WM, CivicPoll as _CP, Petition as _Pet
        from django.utils import timezone as _tz
        upcoming_meeting = _WM.objects.filter(
            ward_number=ward_number, status='SCHEDULED', meeting_date__gte=_tz.now()
        ).order_by('meeting_date').first()
        open_proposals_count = _Prop.objects.filter(
            ward_number=ward_number, status__in=('PENDING', 'REVIEWING')
        ).count()
        ward_active_polls = list(_CP.objects.filter(status='ACTIVE').filter(
            Q(ward_number=ward_number) | Q(ward_number__isnull=True))[:2])
        ward_open_petitions = list(_Pet.objects.filter(
            status='OPEN', ward_number=ward_number).order_by('-signature_count')[:3])
    except Exception:
        pass

    # Is this the logged-in user's ward?
    is_my_ward = request.user.is_authenticated and request.user.ward_number == ward_number

    # Which projects does this user follow?
    followed_project_ids = set()
    if request.user.is_authenticated:
        followed_project_ids = set(
            WardProjectFollow.objects.filter(
                user=request.user, project__ward_number=ward_number
            ).values_list('project_id', flat=True)
        )

    return render(request, 'core/ward_pulse.html', {
        'ward_number':       ward_number,
        'total_complaints':  total_complaints,
        'resolved_count':    resolved_count,
        'in_progress_count': in_progress_count,
        'pending_count':     pending_count,
        'resolution_rate':   resolution_rate,
        'top_categories':    top_categories,
        'top_issues':        top_issues,
        'projects':          projects,
        'active_project_count': active_project_count,
        'budget':            budget,
        'announcements':     announcements,
        'chairperson':       chairperson,
        'avg_rating':        avg_rating,
        'is_my_ward':        is_my_ward,
        'followed_project_ids': followed_project_ids,
        'wards':             range(1, 18),
        'upcoming_meeting':      upcoming_meeting,
        'open_proposals_count':  open_proposals_count,
        'ward_active_polls':     ward_active_polls,
        'ward_open_petitions':   ward_open_petitions,
    })


def ward_chairperson_profile(request, ward_number):
    """Public profile of the ward chairperson."""
    from accounts.models import User
    from complaints.models import Complaint
    from core.models import WardProject, Announcement

    if ward_number < 1 or ward_number > 17:
        from django.http import Http404
        raise Http404

    chairperson = User.objects.filter(role='chairperson', ward_number=ward_number).first()
    ward_qs = Complaint.objects.filter(ward_number=ward_number)
    total = ward_qs.count()
    resolved = ward_qs.filter(status='RESOLVED').count()

    projects = WardProject.objects.filter(ward_number=ward_number).order_by('-created_at')[:6]
    announcements = Announcement.objects.filter(
        ward_number=ward_number, is_active=True
    ).order_by('-created_at')[:5]
    if chairperson:
        announcements = list(announcements.filter(posted_by=chairperson))

    return render(request, 'core/ward_chairperson.html', {
        'ward_number':   ward_number,
        'chairperson':   chairperson,
        'total':         total,
        'resolved':      resolved,
        'resolution_rate': round(resolved / total * 100) if total else 0,
        'projects':      list(projects),
        'announcements': announcements,
    })


@login_required
def announcement_comment(request, pk):
    """POST: add a comment to an announcement."""
    from django.shortcuts import get_object_or_404, redirect
    from core.models import Announcement, AnnouncementComment
    from django.contrib import messages

    announcement = get_object_or_404(Announcement, pk=pk, is_active=True)
    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body and len(body) <= 1000:
            AnnouncementComment.objects.create(
                announcement=announcement,
                user=request.user,
                body=body,
            )
            messages.success(request, 'Comment posted.')
        else:
            messages.error(request, 'Comment must be between 1 and 1000 characters.')
    return redirect(request.META.get('HTTP_REFERER', '/announcements/'))


@login_required
def toggle_project_follow(request, pk):
    """POST: toggle follow/unfollow on a ward project."""
    from django.shortcuts import get_object_or_404
    from core.models import WardProject, WardProjectFollow
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    project = get_object_or_404(WardProject, pk=pk)
    obj, created = WardProjectFollow.objects.get_or_create(
        project=project, user=request.user
    )
    if not created:
        obj.delete()
        following = False
    else:
        following = True

    follower_count = WardProjectFollow.objects.filter(project=project).count()
    return JsonResponse({'following': following, 'count': follower_count})


def robots_txt(request):
    from django.http import HttpResponse
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin/\n"
        "Disallow: /django-admin/\n"
        "Disallow: /api/\n"
        f"Sitemap: https://bhaktapur.gov.np/sitemap.xml\n"
    )
    return HttpResponse(content, content_type='text/plain')


def service_worker(request):
    """Serve versioned service worker from Django template so cache-busting is driven by settings."""
    from django.template.loader import render_to_string
    from django.http import HttpResponse
    content = render_to_string("core/sw.js", {
        "cache_version": getattr(settings, 'STATIC_VERSION', 1),
    })
    response = HttpResponse(content, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


def offline(request):
    """Offline fallback page — shown when the user has no connection."""
    return render(request, 'core/offline.html')


def web_manifest(request):
    """Serve web app manifest from root so browsers can find it."""
    import os
    from django.http import HttpResponse
    from django.conf import settings
    manifest_path = os.path.join(settings.BASE_DIR, 'static', 'manifest.json')
    try:
        with open(manifest_path, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        content = '{}'
    return HttpResponse(content, content_type='application/manifest+json')


def search_suggest_api(request):
    """AJAX endpoint for nav search autocomplete."""
    from django.http import JsonResponse
    from django.db.models import Q
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    results = []

    # Attractions
    try:
        from tourism.models import Attraction
        for a in Attraction.objects.filter(
            Q(name__icontains=q) | Q(description__icontains=q),
            is_active=True
        )[:3]:
            results.append({
                'type': 'attraction', 'label': a.name,
                'url': f'/attractions/{a.slug}/'
            })
    except Exception:
        pass

    # Events
    try:
        from events.models import Event
        from django.utils import timezone
        for e in Event.objects.filter(
            Q(name__icontains=q) | Q(description__icontains=q),
            is_active=True
        )[:3]:
            results.append({
                'type': 'event', 'label': f'{e.name} · {e.start_date.strftime("%b %d")}',
                'url': f'/events/{e.slug}/'
            })
    except Exception:
        pass

    # Businesses
    try:
        from businesses.models import Business
        for b in Business.objects.filter(
            Q(name__icontains=q) | Q(description__icontains=q),
            is_active=True
        )[:3]:
            results.append({
                'type': 'business', 'label': b.name,
                'url': f'/businesses/{b.slug}/'
            })
    except Exception:
        pass

    # Products
    try:
        from marketplace.models import Product
        for p in Product.objects.filter(
            Q(name__icontains=q) | Q(description__icontains=q),
            is_active=True
        )[:3]:
            results.append({
                'type': 'product', 'label': f'{p.name} — NPR {p.get_price()}',
                'url': f'/marketplace/{p.slug}/'
            })
    except Exception:
        pass

    return JsonResponse({'results': results[:8]})

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.core.paginator import Paginator
from django.core.cache import cache
from .models import Event, EventRegistration


def events_list(request):
    category = request.GET.get('category', '')
    when = request.GET.get('when', 'upcoming')
    page_num = request.GET.get('page', '1')
    now = timezone.now()

    # Cache non-personalised, non-paginated first pages for 5 minutes
    _cache_key = None
    if not request.user.is_authenticated and page_num == '1' and not category:
        _cache_key = f'events_list:{when}'
        _cached = cache.get(_cache_key)
        if _cached:
            return _cached

    events = Event.objects.filter(is_active=True)

    if category:
        events = events.filter(category=category)

    if when == 'today':
        from datetime import timedelta
        events = events.filter(start_date__gte=now, start_date__lt=now + timedelta(days=1))
    elif when == 'this_week':
        from datetime import timedelta
        events = events.filter(start_date__gte=now, start_date__lt=now + timedelta(days=7))
    elif when == 'past':
        events = events.filter(start_date__lt=now).order_by('-start_date')
    else:
        events = events.filter(start_date__gte=now).order_by('start_date')

    total_count = events.count()
    paginator = Paginator(events, 12)
    page_obj = paginator.get_page(page_num)
    params = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    response = render(request, 'events/list.html', {
        'events': page_obj,
        'page_obj': page_obj,
        'querystring': querystring,
        'total_count': total_count,
        'active_category': category,
        'when': when,
        'categories': Event.CATEGORY_CHOICES,
    })
    if _cache_key:
        cache.set(_cache_key, response, 300)
    return response


def event_detail(request, slug):
    event = get_object_or_404(Event, slug=slug, is_active=True)
    is_registered = False
    spots_left = None

    if request.user.is_authenticated:
        is_registered = EventRegistration.objects.filter(
            event=event, user=request.user
        ).exists()

    if event.max_attendees:
        registered = EventRegistration.objects.filter(event=event).count()
        spots_left = max(0, event.max_attendees - registered)

    if request.method == 'POST' and request.user.is_authenticated and not is_registered:
        EventRegistration.objects.get_or_create(event=event, user=request.user)
        return redirect('events:event_detail', slug=event.slug)

    return render(request, 'events/detail.html', {
        'event': event,
        'is_registered': is_registered,
        'spots_left': spots_left,
    })


@login_required
@require_POST
def event_register(request, slug):
    event = get_object_or_404(Event, slug=slug, is_active=True)
    with transaction.atomic():
        event = Event.objects.select_for_update().get(pk=event.pk)
        if event.max_attendees:
            count = EventRegistration.objects.filter(event=event).count()
            if count >= event.max_attendees:
                messages.error(request, 'Sorry, this event is fully booked.')
                return redirect('events:event_detail', slug=slug)
        EventRegistration.objects.get_or_create(event=event, user=request.user)
    Event.objects.filter(pk=event.pk).update(
        registration_count=EventRegistration.objects.filter(event=event).count()
    )
    messages.success(request, f'You are registered for {event.name}!')
    return redirect('events:event_detail', slug=slug)


@login_required
@require_POST
def event_unregister(request, slug):
    event = get_object_or_404(Event, slug=slug, is_active=True)
    EventRegistration.objects.filter(event=event, user=request.user).delete()
    Event.objects.filter(pk=event.pk).update(
        registration_count=EventRegistration.objects.filter(event=event).count()
    )
    messages.success(request, f'You have unregistered from {event.name}.')
    return redirect('events:event_detail', slug=slug)

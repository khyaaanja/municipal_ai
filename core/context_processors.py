import datetime
import time
from django.conf import settings
from django.db.models import Q

# Refresh interval (seconds) for session-cached context processor values
_CTX_REFRESH_TTL = 60


def global_context(request):
    cart_count = 0
    unread_notifications = 0
    overdue_count = 0
    pending_proposals_count = 0
    pending_service_requests_count = 0

    if request.user.is_authenticated:
        # Use session caching with a 60-second TTL to avoid DB queries on every page load
        last_refresh = request.session.get('ctx_refresh_at', 0)
        now = time.time()
        if now - last_refresh > _CTX_REFRESH_TTL:
            # Refresh from DB
            try:
                from marketplace.models import CartItem
                cart_count = sum(
                    CartItem.objects.filter(cart__user=request.user)
                    .values_list('quantity', flat=True)
                )
            except Exception:
                cart_count = 0
            request.session['cart_count'] = cart_count

            try:
                from accounts.models import Notification
                unread_notifications = Notification.objects.filter(
                    user=request.user, is_read=False
                ).count()
            except Exception:
                unread_notifications = 0
            request.session['unread_notifications'] = unread_notifications

            # Overdue count for staff/mayor/chairperson
            if request.user.role in ('mayor', 'chairperson'):
                try:
                    from complaints.models import Complaint
                    from django.utils import timezone as _tz
                    dt_now = _tz.now()
                    qs = Complaint.objects.exclude(status__in=('RESOLVED', 'REJECTED'))
                    if request.user.role == 'chairperson' and request.user.ward_number:
                        qs = qs.filter(ward_number=request.user.ward_number)
                    overdue_count = qs.filter(
                        Q(priority='CRITICAL', created_at__lt=dt_now - datetime.timedelta(days=1)) |
                        Q(priority='HIGH',     created_at__lt=dt_now - datetime.timedelta(days=3)) |
                        Q(priority='MEDIUM',   created_at__lt=dt_now - datetime.timedelta(days=7)) |
                        Q(priority='LOW',      created_at__lt=dt_now - datetime.timedelta(days=14))
                    ).count()
                except Exception:
                    overdue_count = 0
                request.session['overdue_count'] = overdue_count

            # Chairperson-specific counts
            if request.user.role == 'chairperson':
                ward = getattr(request.user, 'ward_number', None)
                if ward:
                    try:
                        from civic.models import Proposal
                        from services.models import ServiceRequest
                        pending_proposals_count = Proposal.objects.filter(
                            ward_number=ward, status='PENDING').count()
                        pending_service_requests_count = ServiceRequest.objects.filter(
                            ward_number=ward, status='SUBMITTED').count()
                    except Exception:
                        pending_proposals_count = 0
                        pending_service_requests_count = 0
                    request.session['pending_proposals_count'] = pending_proposals_count
                    request.session['pending_service_requests_count'] = pending_service_requests_count

            request.session['ctx_refresh_at'] = now
        else:
            cart_count = request.session.get('cart_count', 0)
            unread_notifications = request.session.get('unread_notifications', 0)
            overdue_count = request.session.get('overdue_count', 0)
            pending_proposals_count = request.session.get('pending_proposals_count', 0)
            pending_service_requests_count = request.session.get('pending_service_requests_count', 0)

    is_tourist_pass = bool(request.session.get('tourist_pass', False))
    if is_tourist_pass:
        created = request.session.get('tourist_created', 0)
        if time.time() - created > 86400:  # auto-expire after 24 hours
            request.session.pop('tourist_pass', None)
            request.session.pop('tourist_name', None)
            request.session.pop('tourist_created', None)
            is_tourist_pass = False
    tourist_name = request.session.get('tourist_name', 'Traveller') if is_tourist_pass else ''

    return {
        'CITY_NAME': settings.CITY_NAME,
        'CITY_COUNTRY': settings.CITY_COUNTRY,
        'CITY_LAT': settings.CITY_LAT,
        'CITY_LNG': settings.CITY_LNG,
        'cart_count': cart_count,
        'unread_notifications': unread_notifications,
        'overdue_count': overdue_count,
        'pending_proposals_count': pending_proposals_count,
        'pending_service_requests_count': pending_service_requests_count,
        'is_tourist_pass': is_tourist_pass,
        'tourist_name': tourist_name,
    }

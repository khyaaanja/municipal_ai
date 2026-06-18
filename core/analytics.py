from core.utils import get_client_ip


def track(request, action: str, object_type: str = '', object_id: int = None, extra: dict = None):
    """Fire-and-forget analytics. Never raises — analytics must never crash the app."""
    try:
        from core.models import Analytics
        Analytics.objects.create(
            action=action,
            user=request.user if request.user.is_authenticated else None,
            session_key=request.session.session_key or '',
            object_type=object_type,
            object_id=object_id,
            extra_data=extra or {},
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        )
    except Exception:
        pass

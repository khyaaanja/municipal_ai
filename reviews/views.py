import logging

from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .models import Review

logger = logging.getLogger(__name__)


@login_required
@require_POST
def submit_review(request):
    content_type = request.POST.get('content_type')
    object_id = request.POST.get('object_id')
    comment = request.POST.get('comment', '').strip()
    next_url = request.POST.get('next', '/')

    valid_types = [c[0] for c in Review.CONTENT_TYPE_CHOICES]
    if content_type not in valid_types:
        return redirect(next_url)

    try:
        rating = max(1, min(5, int(request.POST.get('rating', 5))))
        obj_id = int(object_id)
    except (ValueError, TypeError):
        return redirect(next_url)

    if obj_id and comment:
        Review.objects.update_or_create(
            user=request.user,
            content_type=content_type,
            object_id=obj_id,
            defaults={'rating': rating, 'comment': comment}
        )
        # Keep Business denormalized rating in sync
        if content_type == 'business':
            try:
                from businesses.models import Business
                from django.db.models import Avg, Count
                agg = Review.objects.filter(
                    content_type='business', object_id=obj_id
                ).aggregate(avg=Avg('rating'), cnt=Count('id'))
                Business.objects.filter(pk=obj_id).update(
                    avg_rating=agg['avg'] or 0,
                    review_count=agg['cnt'],
                )
            except Exception:
                logger.exception("Failed to update denormalized rating for business %s", obj_id)
    return redirect(next_url)

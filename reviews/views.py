from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .models import Review


@login_required
@require_POST
def submit_review(request):
    content_type = request.POST.get('content_type')
    object_id = request.POST.get('object_id')
    comment = request.POST.get('comment', '').strip()
    next_url = request.POST.get('next', '/')

    try:
        rating = max(1, min(5, int(request.POST.get('rating', 5))))
        obj_id = int(object_id)
    except (ValueError, TypeError):
        return redirect(next_url)

    if content_type and obj_id and comment:
        Review.objects.update_or_create(
            user=request.user,
            content_type=content_type,
            object_id=obj_id,
            defaults={'rating': rating, 'comment': comment}
        )
    return redirect(next_url)

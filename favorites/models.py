from django.db import models
from django.conf import settings


class Favorite(models.Model):
    CONTENT_TYPE_CHOICES = [
        ('attraction', 'Attraction'),
        ('business', 'Business'),
        ('event', 'Event'),
        ('product', 'Product'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites'
    )
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    object_id = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'favorites'
        unique_together = ['user', 'content_type', 'object_id']

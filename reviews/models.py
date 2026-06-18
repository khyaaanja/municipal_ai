from django.db import models
from django.conf import settings


class Review(models.Model):
    CONTENT_TYPE_CHOICES = [
        ('attraction', 'Attraction'),
        ('business', 'Business'),
        ('event', 'Event'),
        ('product', 'Product'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    object_id = models.IntegerField()
    rating = models.IntegerField()  # 1-5
    title = models.CharField(max_length=200, blank=True)
    comment = models.TextField()
    is_approved = models.BooleanField(default=True)
    is_flagged = models.BooleanField(default=False)
    helpful_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reviews'
        unique_together = ['user', 'content_type', 'object_id']
        ordering = ['-created_at']

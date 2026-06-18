from django.db import models
from django.conf import settings


class Itinerary(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='itineraries'
    )
    title = models.CharField(max_length=200)
    days = models.IntegerField()
    budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    budget_currency = models.CharField(max_length=10, default='NPR')
    interests = models.JSONField(default=list, blank=True)
    group_type = models.CharField(max_length=50, blank=True)
    group_size = models.IntegerField(default=1)
    generated_plan = models.JSONField(default=dict)
    is_saved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.days} days)"

    class Meta:
        db_table = 'itineraries'
        ordering = ['-created_at']

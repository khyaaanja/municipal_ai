from django.db import models
from django.conf import settings


class EventCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'event_categories'
        verbose_name_plural = 'Event Categories'


class Event(models.Model):
    CATEGORY_CHOICES = [
        ('festival', 'Festival'),
        ('concert', 'Concert'),
        ('exhibition', 'Exhibition'),
        ('cultural', 'Cultural'),
        ('sports', 'Sports'),
        ('workshop', 'Workshop'),
        ('food', 'Food & Drink'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='other')
    venue = models.CharField(max_length=200, blank=True)
    address = models.CharField(max_length=300, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    organizer = models.CharField(max_length=200, blank=True)
    cover_image = models.ImageField(upload_to='events/', null=True, blank=True)
    entry_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_free = models.BooleanField(default=True)
    max_attendees = models.IntegerField(null=True, blank=True)
    schedule = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    registration_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'events'
        ordering = ['start_date']
        indexes = [
            models.Index(fields=['is_active', 'start_date'], name='event_active_start_idx'),
            models.Index(fields=['is_featured'], name='event_featured_idx'),
        ]


class EventRegistration(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='registrations')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    registered_at = models.DateTimeField(auto_now_add=True)
    attended = models.BooleanField(default=False)

    class Meta:
        db_table = 'event_registrations'
        unique_together = ['event', 'user']

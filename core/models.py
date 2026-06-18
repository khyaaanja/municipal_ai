from django.db import models
from django.conf import settings


class Analytics(models.Model):
    ACTION_CHOICES = [
        ('page_view',         'Page View'),
        ('search',            'Search'),
        ('chat',              'Chat'),
        ('attraction_view',   'Attraction View'),
        ('event_view',        'Event View'),
        ('business_view',     'Business View'),
        ('product_view',      'Product View'),
        ('order_placed',      'Order Placed'),
        ('complaint_submit',  'Complaint Submitted'),
        ('complaint_view',    'Complaint Viewed'),
        ('review_submit',     'Review Submitted'),
        ('login',             'Login'),
        ('logout',            'Logout'),
        ('register',          'Register'),
        ('cart_add',          'Cart Add'),
        ('cart_remove',       'Cart Remove'),
        ('news_view',         'News View'),
        ('map_view',          'Map View'),
    ]

    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True
    )
    session_key = models.CharField(max_length=100, blank=True)
    object_type = models.CharField(max_length=50, blank=True)
    object_id = models.IntegerField(null=True, blank=True)
    extra_data = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'analytics'


class SiteSettings(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key

    class Meta:
        db_table = 'site_settings'
        verbose_name_plural = 'Site Settings'

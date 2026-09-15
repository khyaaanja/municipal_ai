from django.db import models
from django.conf import settings


class Business(models.Model):
    CATEGORY_CHOICES = [
        ('restaurant', 'Restaurant'),
        ('hotel', 'Hotel'),
        ('cafe', 'Café'),
        ('shop', 'Shop'),
        ('service', 'Service'),
        ('pharmacy', 'Pharmacy'),
        ('bank', 'Bank'),
        ('transport', 'Transport'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='other')
    address = models.CharField(max_length=300, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    opening_hours = models.CharField(max_length=300, blank=True)
    cover_image = models.ImageField(upload_to='businesses/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    avg_rating = models.FloatField(null=True, blank=True)
    review_count = models.IntegerField(default=0)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='businesses'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_open(self):
        """Parse opening_hours "HH:MM-HH:MM" and compare against local time."""
        if not self.opening_hours:
            return None
        import re
        from django.utils import timezone as _tz
        m = re.match(r'(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})', self.opening_hours)
        if not m:
            return None
        now = _tz.localtime(_tz.now()).time()
        import datetime
        open_t  = datetime.time(int(m.group(1)), int(m.group(2)))
        close_t = datetime.time(int(m.group(3)), int(m.group(4)))
        return open_t <= now <= close_t

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'businesses'
        verbose_name_plural = 'Businesses'
        ordering = ['-is_featured', '-review_count']
        indexes = [
            models.Index(fields=['is_active', 'is_featured'], name='business_active_featured_idx'),
            models.Index(fields=['category'], name='business_category_idx'),
        ]

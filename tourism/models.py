from django.db import models
from django.conf import settings


class AttractionCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    icon = models.CharField(max_length=10, blank=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'attraction_categories'
        verbose_name_plural = 'Attraction Categories'


class Attraction(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    category = models.ForeignKey(
        AttractionCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='attractions'
    )
    address = models.CharField(max_length=300, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    opening_hours = models.CharField(max_length=200, blank=True)
    entry_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_free = models.BooleanField(default=False)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    view_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def is_open_now(self):
        return True  # Placeholder — can implement with actual hours parsing

    class Meta:
        db_table = 'attractions'
        ordering = ['-is_featured', '-view_count']
        indexes = [
            models.Index(fields=['is_active', 'is_featured'], name='attraction_active_featured_idx'),
            models.Index(fields=['category'], name='attraction_category_idx'),
        ]


class AttractionImage(models.Model):
    attraction = models.ForeignKey(
        Attraction, on_delete=models.CASCADE, related_name='images'
    )
    image = models.ImageField(upload_to='attractions/')
    caption = models.CharField(max_length=200, blank=True)
    is_cover = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'attraction_images'
        ordering = ['-is_cover', 'order']

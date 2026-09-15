from django.db import models
from django.conf import settings
from django.utils import timezone


class NewsArticle(models.Model):
    CATEGORY_CHOICES = [
        ('announcement', 'Municipal Announcement'),
        ('tourism', 'Tourism Update'),
        ('alert', 'City Alert'),
        ('event', 'Event News'),
        ('development', 'City Development'),
        ('general', 'General News'),
    ]

    title = models.CharField(max_length=300)
    slug = models.SlugField(unique=True)
    summary = models.CharField(max_length=500)
    content = models.TextField()
    cover_image = models.ImageField(upload_to='news/', null=True, blank=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='general')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    is_pinned = models.BooleanField(default=False)
    view_count = models.IntegerField(default=0)
    published_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        db_table = 'news'
        ordering = ['-is_pinned', '-published_at']

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


class Announcement(models.Model):
    title      = models.CharField(max_length=200)
    body       = models.TextField()
    ward_number = models.IntegerField(null=True, blank=True, help_text='null = city-wide')
    posted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='announcements'
    )
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'announcements'
        ordering = ['-created_at']

    def __str__(self):
        scope = f'Ward {self.ward_number}' if self.ward_number else 'City-wide'
        return f'[{scope}] {self.title}'


class WardProject(models.Model):
    STATUS_CHOICES = [
        ('PLANNED',     'Planned'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED',   'Completed'),
        ('ON_HOLD',     'On Hold'),
    ]
    ward_number  = models.IntegerField()
    title        = models.CharField(max_length=200)
    description  = models.TextField(blank=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PLANNED')
    progress_pct = models.IntegerField(default=0)
    budget       = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    start_date   = models.DateField(null=True, blank=True)
    end_date     = models.DateField(null=True, blank=True)
    created_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ward_projects'
    )
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ward_projects'
        ordering = ['-created_at']

    def __str__(self):
        return f'Ward {self.ward_number}: {self.title}'


class WardBudget(models.Model):
    ward_number       = models.IntegerField()
    fiscal_year       = models.CharField(max_length=9, default='2081-82')
    total_allocation  = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    spent             = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes             = models.TextField(blank=True)
    updated_by        = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='budget_updates'
    )
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ward_budgets'
        unique_together = [('ward_number', 'fiscal_year')]

    def __str__(self):
        return f'Ward {self.ward_number} Budget {self.fiscal_year}'

    @property
    def remaining(self):
        return self.total_allocation - self.spent

    @property
    def spend_pct(self):
        if self.total_allocation:
            return min(100, round(float(self.spent) / float(self.total_allocation) * 100))
        return 0


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


class AnnouncementComment(models.Model):
    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE, related_name='comments'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='announcement_comments'
    )
    body = models.TextField(max_length=1000)
    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'announcement_comments'
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.user.email} on '{self.announcement.title[:40]}'"


class WardProjectFollow(models.Model):
    project = models.ForeignKey(
        WardProject, on_delete=models.CASCADE, related_name='followers'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='followed_projects'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ward_project_follows'
        unique_together = [('project', 'user')]

    def __str__(self):
        return f"{self.user.email} follows Ward {self.project.ward_number}: {self.project.title[:40]}"

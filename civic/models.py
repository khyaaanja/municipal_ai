from django.db import models
from django.conf import settings


class Proposal(models.Model):
    CATEGORY_CHOICES = [
        ('INFRASTRUCTURE', 'Infrastructure'),
        ('SANITATION',     'Sanitation'),
        ('ENVIRONMENT',    'Environment'),
        ('EDUCATION',      'Education'),
        ('HEALTH',         'Health'),
        ('CULTURE',        'Culture'),
        ('SAFETY',         'Safety'),
        ('OTHER',          'Other'),
    ]
    STATUS_CHOICES = [
        ('PENDING',     'Pending'),
        ('REVIEWING',   'Reviewing'),
        ('ACCEPTED',    'Accepted'),
        ('REJECTED',    'Rejected'),
        ('IMPLEMENTED', 'Implemented'),
    ]

    ward_number      = models.IntegerField(db_index=True)
    submitted_by     = models.ForeignKey(
                         settings.AUTH_USER_MODEL,
                         on_delete=models.CASCADE,
                         related_name='proposals')
    category         = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    title            = models.CharField(max_length=200)
    description      = models.TextField()
    expected_benefit = models.TextField(blank=True)
    estimated_cost   = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status           = models.CharField(max_length=12, choices=STATUS_CHOICES,
                                        default='PENDING', db_index=True)
    chairperson_note = models.TextField(blank=True)
    reviewed_by      = models.ForeignKey(
                         settings.AUTH_USER_MODEL,
                         on_delete=models.SET_NULL,
                         null=True, blank=True,
                         related_name='reviewed_proposals')
    reviewed_at      = models.DateTimeField(null=True, blank=True)
    support_count    = models.IntegerField(default=0)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'civic_proposals'
        indexes = [models.Index(fields=['ward_number', 'status'])]

    def __str__(self):
        return self.title


class ProposalSupport(models.Model):
    proposal   = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name='supporters')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='supported_proposals')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'civic_proposal_supports'
        unique_together = ('proposal', 'user')


class WardMeeting(models.Model):
    STATUS_CHOICES = [
        ('SCHEDULED', 'Scheduled'),
        ('CANCELLED',  'Cancelled'),
        ('COMPLETED',  'Completed'),
    ]

    ward_number  = models.IntegerField(db_index=True)
    title        = models.CharField(max_length=200)
    description  = models.TextField(blank=True)
    venue        = models.CharField(max_length=300)
    meeting_date = models.DateTimeField()
    agenda       = models.TextField(blank=True)
    max_rsvp     = models.IntegerField(null=True, blank=True)
    status       = models.CharField(max_length=12, choices=STATUS_CHOICES, default='SCHEDULED')
    minutes      = models.TextField(blank=True)
    created_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'civic_ward_meetings'
        indexes = [models.Index(fields=['ward_number', 'meeting_date'])]

    def __str__(self):
        return self.title


class MeetingRSVP(models.Model):
    meeting    = models.ForeignKey(WardMeeting, on_delete=models.CASCADE, related_name='rsvps')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='meeting_rsvps')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'civic_meeting_rsvps'
        unique_together = ('meeting', 'user')


class MeetingQuestion(models.Model):
    STATUS_CHOICES = [
        ('PENDING',   'Pending'),
        ('ADDRESSED', 'Addressed'),
        ('DECLINED',  'Declined'),
    ]

    meeting           = models.ForeignKey(WardMeeting, on_delete=models.CASCADE,
                                          related_name='questions')
    asked_by          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                          related_name='meeting_questions')
    question          = models.TextField(max_length=500)
    status            = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    chairperson_reply = models.TextField(blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'civic_meeting_questions'


class CivicPoll(models.Model):
    STATUS_CHOICES = [
        ('DRAFT',  'Draft'),
        ('ACTIVE', 'Active'),
        ('CLOSED', 'Closed'),
    ]

    ward_number  = models.IntegerField(null=True, blank=True)
    question     = models.CharField(max_length=300)
    description  = models.TextField(blank=True)
    status       = models.CharField(max_length=8, choices=STATUS_CHOICES, default='DRAFT')
    closes_at    = models.DateTimeField(null=True, blank=True)
    created_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='created_polls')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'civic_polls'

    def __str__(self):
        return self.question


class PollOption(models.Model):
    poll       = models.ForeignKey(CivicPoll, on_delete=models.CASCADE, related_name='options')
    text       = models.CharField(max_length=200)
    order      = models.PositiveSmallIntegerField(default=0)
    vote_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'civic_poll_options'
        ordering = ['order']

    def __str__(self):
        return self.text


class PollVote(models.Model):
    poll     = models.ForeignKey(CivicPoll, on_delete=models.CASCADE, related_name='votes')
    option   = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name='votes')
    user     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='poll_votes')
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'civic_poll_votes'
        unique_together = ('poll', 'user')


class Petition(models.Model):
    STATUS_CHOICES = [
        ('OPEN',      'Open'),
        ('CLOSED',    'Closed'),
        ('DELIVERED', 'Delivered'),
        ('RESPONDED', 'Responded'),
    ]

    ward_number       = models.IntegerField(null=True, blank=True)
    created_by        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                          related_name='petitions')
    title             = models.CharField(max_length=200)
    body              = models.TextField()
    target            = models.CharField(max_length=200)
    goal_signatures   = models.IntegerField(default=100)
    signature_count   = models.IntegerField(default=0)
    status            = models.CharField(max_length=10, choices=STATUS_CHOICES, default='OPEN')
    official_response = models.TextField(blank=True)
    closes_at         = models.DateTimeField(null=True, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'civic_petitions'

    def __str__(self):
        return self.title

    @property
    def progress_pct(self):
        if self.goal_signatures == 0:
            return 0
        return min(100, int(self.signature_count * 100 / self.goal_signatures))


class PetitionSignature(models.Model):
    petition  = models.ForeignKey(Petition, on_delete=models.CASCADE, related_name='signatures')
    user      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name='petition_signatures')
    comment   = models.CharField(max_length=300, blank=True)
    signed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'civic_petition_signatures'
        unique_together = ('petition', 'user')
        ordering = ['-signed_at']

from django.db import models
from django.conf import settings


class Conversation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True, related_name='conversations'
    )
    session_key = models.CharField(max_length=100, blank=True)
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Conversation {self.id} - {self.user or 'Guest'}"

    class Meta:
        db_table = 'conversations'
        ordering = ['-updated_at']


class Message(models.Model):
    ROLE_USER = 'user'
    ROLE_ASSISTANT = 'assistant'
    ROLE_SYSTEM = 'system'

    ROLE_CHOICES = [
        (ROLE_USER, 'User'),
        (ROLE_ASSISTANT, 'Assistant'),
        (ROLE_SYSTEM, 'System'),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    sources = models.JSONField(default=list)
    intent = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'messages'
        ordering = ['created_at']


class KnowledgeBase(models.Model):
    CATEGORY_CHOICES = [
        ('general', 'General City Info'),
        ('heritage', 'Heritage & Monuments'),
        ('culture', 'Culture & Festivals'),
        ('transport', 'Transportation'),
        ('emergency', 'Emergency Contacts'),
        ('services', 'City Services'),
        ('rules', 'Rules & Guidelines'),
    ]

    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('ne', 'Nepali (नेपाली)'),
        ('hi', 'Hindi (हिंदी)'),
        ('zh-cn', 'Chinese Simplified'),
        ('bn', 'Bengali (বাংলা)'),
    ]

    title = models.CharField(max_length=200)
    content = models.TextField()
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    language = models.CharField(max_length=10, default='en', choices=LANGUAGE_CHOICES, db_index=True)
    keywords = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0)
    # Self-learning fields
    embedding = models.JSONField(null=True, blank=True)       # stored vector from Groq embeddings API
    auto_generated = models.BooleanField(default=False)       # True = written by AI from conversation
    source_query = models.TextField(blank=True)               # original user query that generated this
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        db_table = 'knowledge_base'
        ordering = ['-priority']


class UnansweredQuery(models.Model):
    """Questions the AI couldn't answer well. Admin reviews → adds KB entries."""
    query = models.TextField()
    normalized = models.CharField(max_length=300, blank=True, db_index=True)
    ask_count = models.PositiveIntegerField(default=1)
    is_resolved = models.BooleanField(default=False)
    resolution_kb = models.ForeignKey(
        KnowledgeBase, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='resolved_queries'
    )
    first_asked = models.DateTimeField(auto_now_add=True)
    last_asked = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'unanswered_queries'
        ordering = ['-ask_count', '-last_asked']

    def __str__(self):
        return f"({self.ask_count}x) {self.query[:80]}"


class ResponseFeedback(models.Model):
    HELPFUL = 1
    NOT_HELPFUL = -1
    RATING_CHOICES = [(HELPFUL, 'Helpful'), (NOT_HELPFUL, 'Not Helpful')]

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='feedback')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ai_feedback'
    )
    session_key = models.CharField(max_length=100, blank=True)
    rating = models.SmallIntegerField(choices=RATING_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'response_feedback'

    def __str__(self):
        return f"{'👍' if self.rating == 1 else '👎'} on message {self.message_id}"


class UserAIProfile(models.Model):
    """Per-user preferences and context learned from conversations."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='ai_profile'
    )
    preferences = models.JSONField(default=dict)           # {"dietary": "vegetarian", "budget": "low"}
    visited_attractions = models.JSONField(default=list)   # ["Nyatapola Temple", ...]
    conversation_summary = models.TextField(blank=True)    # rolling summary of past chats
    preferred_language = models.CharField(max_length=10, default='en', choices=[
        ('en', 'English'),
        ('ne', 'Nepali (नेपाली)'),
        ('hi', 'Hindi (हिंदी)'),
        ('zh-cn', 'Chinese Simplified'),
        ('bn', 'Bengali (বাংলা)'),
    ])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_ai_profiles'

    def __str__(self):
        return f"AI Profile — {self.user}"


class FAQEntry(models.Model):
    """
    Municipal FAQ pairs for the fallback answer path.

    Anything answerable in a fixed way (office hours, required documents, fees)
    lives here — checked *first* before Groq when there's a high-confidence
    keyword match, and used to build extractive fallback answers.
    """
    question = models.TextField()
    answer = models.TextField()
    category = models.CharField(
        max_length=50,
        choices=[
            ('documents', 'Documents'),
            ('tax', 'Tax'),
            ('tourism', 'Tourism'),
            ('services', 'Municipal Services'),
            ('emergency', 'Emergency Contacts'),
            ('procedures', 'Procedures'),
            ('general', 'General'),
        ],
        default='general',
        db_index=True,
    )
    keywords = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'faq_entries'
        ordering = ['-updated_at']

    def __str__(self):
        return self.question[:80]


class KnowledgeChunk(models.Model):
    """
    Long-form knowledge chunks for embedding into the vector store
    (ChromaDB today, pgvector after migration). Used by the fallback
    answer path when the LLM is unavailable.
    """
    source_type = models.CharField(
        max_length=50,
        choices=[
            ('tourism', 'Tourism'),
            ('procedure', 'Procedure'),
            ('service', 'Municipal Service'),
            ('heritage', 'Heritage'),
            ('culture', 'Culture'),
            ('transport', 'Transport'),
            ('emergency', 'Emergency'),
            ('general', 'General'),
        ],
        default='general',
        db_index=True,
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    embedding_id = models.CharField(max_length=100, null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'knowledge_chunks'
        ordering = ['-updated_at']

    def __str__(self):
        return self.title

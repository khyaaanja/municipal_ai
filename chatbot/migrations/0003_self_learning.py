from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0002_semantic_embedding'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Replace embedding_placeholder with real self-learning fields on KnowledgeBase
        migrations.RemoveField(
            model_name='knowledgebase',
            name='embedding_placeholder',
        ),
        migrations.AddField(
            model_name='knowledgebase',
            name='embedding',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='knowledgebase',
            name='auto_generated',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='knowledgebase',
            name='source_query',
            field=models.TextField(blank=True),
        ),

        # UnansweredQuery — logs questions the AI couldn't answer
        migrations.CreateModel(
            name='UnansweredQuery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('query', models.TextField()),
                ('normalized', models.CharField(blank=True, db_index=True, max_length=300)),
                ('ask_count', models.PositiveIntegerField(default=1)),
                ('is_resolved', models.BooleanField(default=False)),
                ('resolution_kb', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='resolved_queries',
                    to='chatbot.knowledgebase',
                )),
                ('first_asked', models.DateTimeField(auto_now_add=True)),
                ('last_asked', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'unanswered_queries',
                'ordering': ['-ask_count', '-last_asked'],
            },
        ),

        # ResponseFeedback — thumbs up/down on AI responses
        migrations.CreateModel(
            name='ResponseFeedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('message', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='feedback',
                    to='chatbot.message',
                )),
                ('user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='ai_feedback',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('session_key', models.CharField(blank=True, max_length=100)),
                ('rating', models.SmallIntegerField(choices=[(1, 'Helpful'), (-1, 'Not Helpful')])),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'response_feedback',
            },
        ),

        # UserAIProfile — per-user preferences learned from conversations
        migrations.CreateModel(
            name='UserAIProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='ai_profile',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('preferences', models.JSONField(default=dict)),
                ('visited_attractions', models.JSONField(default=list)),
                ('conversation_summary', models.TextField(blank=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'user_ai_profiles',
            },
        ),
    ]

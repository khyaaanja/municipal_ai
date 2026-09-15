import uuid
from django.db import migrations, models


def populate_verification_tokens(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    for user in User.objects.filter(email_verification_token__isnull=True):
        user.email_verification_token = uuid.uuid4()
        user.save(update_fields=['email_verification_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_add_otp_fields'),
    ]

    operations = [
        # Step 1: Add nullable (no unique yet)
        migrations.AddField(
            model_name='user',
            name='email_verification_token',
            field=models.UUIDField(null=True, blank=True),
        ),
        # Step 2: Expand otp_secret to 256 chars to hold encrypted ciphertext
        migrations.AlterField(
            model_name='user',
            name='otp_secret',
            field=models.CharField(blank=True, default='', max_length=256),
        ),
        # Step 3: Populate tokens for existing rows
        migrations.RunPython(populate_verification_tokens, migrations.RunPython.noop),
        # Step 4: Make unique and non-nullable
        migrations.AlterField(
            model_name='user',
            name='email_verification_token',
            field=models.UUIDField(default=uuid.uuid4, unique=True, db_index=True),
        ),
    ]

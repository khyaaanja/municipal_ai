from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='user',
            old_name='role',
            new_name='legacy_role',
        ),
        migrations.AddField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('citizen',  'Citizen'),
                    ('staff',    'Municipality Staff'),
                    ('official', 'Municipality Official'),
                    ('admin',    'Platform Admin'),
                ],
                db_index=True,
                default='citizen',
                max_length=20,
            ),
        ),
    ]

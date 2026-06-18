from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('complaints', '0002_complaintstatuslog'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ComplaintStatusLog',
        ),
    ]

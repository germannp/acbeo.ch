# Generated by Django 4.0.4 on 2022-05-08 12:37

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('trainings', '0002_training_max_pilots'),
    ]

    operations = [
        migrations.AddField(
            model_name='training',
            name='emergency_mail_sender',
            field=models.ForeignKey(blank=True, db_index=False, default=None, null=True, on_delete=django.db.models.deletion.SET_DEFAULT, to=settings.AUTH_USER_MODEL),
        ),
    ]

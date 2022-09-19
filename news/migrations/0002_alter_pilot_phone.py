# Generated by Django 4.1.1 on 2022-09-16 20:09

from django.db import migrations, models
import news.models


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pilot",
            name="phone",
            field=models.CharField(
                max_length=20, validators=[news.models.validate_phone]
            ),
        ),
    ]

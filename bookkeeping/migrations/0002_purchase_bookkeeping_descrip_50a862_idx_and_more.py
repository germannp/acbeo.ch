# Generated by Django 4.2.1 on 2023-09-05 20:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookkeeping", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="purchase",
            index=models.Index(
                fields=["description"], name="bookkeeping_descrip_50a862_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="run",
            index=models.Index(
                fields=["created_on"], name="bookkeeping_created_e59385_idx"
            ),
        ),
    ]

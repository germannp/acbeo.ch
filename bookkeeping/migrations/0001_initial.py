# Generated by Django 4.1.1 on 2022-11-13 13:51

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("trainings", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Report",
            fields=[
                (
                    "training",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        serialize=False,
                        to="trainings.training",
                    ),
                ),
                ("cash_at_start", models.SmallIntegerField()),
                ("cash_at_end", models.SmallIntegerField()),
            ],
        ),
    ]
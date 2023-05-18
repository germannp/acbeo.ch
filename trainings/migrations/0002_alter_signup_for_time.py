# Generated by Django 4.1.1 on 2023-04-29 17:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trainings", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="signup",
            name="for_time",
            field=models.SmallIntegerField(
                choices=[
                    (1, "All Day"),
                    (2, "Arriving Late"),
                    (3, "Leaving Early"),
                    (4, "Individually"),
                ],
                default=1,
            ),
        ),
    ]
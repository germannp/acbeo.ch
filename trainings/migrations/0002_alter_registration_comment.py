# Generated by Django 3.2.12 on 2022-04-16 21:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trainings', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='registration',
            name='comment',
            field=models.CharField(default='', max_length=200),
        ),
    ]

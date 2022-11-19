from django.db import models

from trainings.models import Training


class Report(models.Model):
    training = models.OneToOneField(
        Training, on_delete=models.CASCADE, primary_key=True
    )
    cash_at_start = models.SmallIntegerField()
    cash_at_end = models.SmallIntegerField(blank=True, null=True)

    def __str__(self):
        return f"{self.training}"

from django.core.validators import MinValueValidator
from django.db import models

from trainings.models import Training


class Report(models.Model):
    training = models.OneToOneField(
        Training, on_delete=models.CASCADE, primary_key=True
    )
    cash_at_start = models.SmallIntegerField(validators=[MinValueValidator(0)])
    cash_at_end = models.SmallIntegerField(
        blank=True, null=True, validators=[MinValueValidator(0)]
    )

    def __str__(self):
        return f"{self.training}"

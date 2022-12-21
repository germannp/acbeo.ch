from django.conf import settings
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


class Run(models.Model):
    Kind = models.IntegerChoices("Kind", "Flight Bus Boat Break")

    pilot = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="runs"
    )
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="runs")
    kind = models.SmallIntegerField(choices=Kind.choices)
    created_on = models.DateTimeField()

    class Meta:
        unique_together = (("pilot", "report", "created_on"),)
        ordering = ("report", "created_on", "pilot")

    def __str__(self):
        return f"{self.pilot} {self.get_kind_display()} on {self.report}"

    @property
    def is_relevant_for_bill(self):
        return self.kind != self.Kind.Break

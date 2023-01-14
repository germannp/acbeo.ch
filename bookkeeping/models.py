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

    @property
    def details(self):
        """Compute details in one place, to keep database calls low"""
        revenue = sum(bill.payed for bill in self.bills.all())
        if self.cash_at_end:
            difference = (self.cash_at_end) - (self.cash_at_start + revenue)
        else:
            difference = None
        return {
            "revenue": revenue,
            "difference": difference,
        }


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

    @property
    def is_flight(self):
        return self.kind == self.Kind.Flight

    @property
    def is_service(self):
        return self.kind in (self.Kind.Bus, self.Kind.Boat)


class Bill(models.Model):
    PRICE_OF_FLIGHT = 9

    pilot = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bills"
    )
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="bills")
    payed = models.SmallIntegerField()

    class Meta:
        unique_together = (("pilot", "report"),)

    def __str__(self):
        return f"{self.pilot} for {self.report}"

    @property
    def details(self):
        """Compute details in one place, to keep database calls low"""
        runs = self.report.runs.filter(pilot=self.pilot)
        num_flights = len([run for run in runs if run.is_flight])
        num_services = len([run for run in runs if run.is_service])
        return {
            "num_flights": num_flights,
            "costs_flights": num_flights * self.PRICE_OF_FLIGHT,
            "num_services": num_services,
            "costs_services": -num_services * self.PRICE_OF_FLIGHT,
            "to_pay": (num_flights - num_services) * self.PRICE_OF_FLIGHT,
        }

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from trainings.models import Signup, Training


class Report(models.Model):
    training = models.OneToOneField(
        Training, on_delete=models.CASCADE, primary_key=True
    )
    cash_at_start = models.SmallIntegerField(validators=[MinValueValidator(0)])
    cash_at_end = models.SmallIntegerField(
        blank=True, null=True, validators=[MinValueValidator(0)]
    )
    remarks = models.CharField(max_length=300, default="", blank=True)

    def __str__(self):
        return f"{self.training}"

    @property
    def details(self):
        """Compute details in one place, to keep database calls low"""
        bills = self.bills.all()
        revenue = sum(bill.payed for bill in bills)
        expenses = sum(expense.amount for expense in self.expenses.all())
        if self.cash_at_end:
            difference = (self.cash_at_end) - (self.cash_at_start + revenue - expenses)
        else:
            difference = None
        return {
            "revenue": revenue,
            "expenses": expenses,
            "difference": difference,
            "num_bills": len(bills),
        }


class Run(models.Model):
    Kind = models.IntegerChoices("Kind", "Flight Bus Boat Break")

    signup = models.ForeignKey(Signup, on_delete=models.CASCADE, related_name="runs")
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="runs")
    kind = models.SmallIntegerField(choices=Kind.choices)
    created_on = models.DateTimeField()

    class Meta:
        unique_together = (("signup", "report", "created_on"),)
        ordering = ("report", "created_on", "signup__pilot")

    def __str__(self):
        return f"{self.signup.pilot} {self.get_kind_display()} on {self.report}"

    @property
    def is_relevant_for_bill(self):
        return self.kind != self.Kind.Break

    @property
    def is_flight(self):
        return self.kind == self.Kind.Flight

    @property
    def is_service(self):
        return self.kind in (self.Kind.Bus, self.Kind.Boat)

    def save(self, *args, **kwargs):
        if self.signup.is_payed:
            raise ValidationError(f"{self.signup.pilot} hat bereits bezahlt.")
        super().save(*args, **kwargs)


class Expense(models.Model):
    report = models.ForeignKey(
        Report, on_delete=models.CASCADE, related_name="expenses"
    )
    reason = models.CharField(max_length=50)
    amount = models.SmallIntegerField(validators=[MinValueValidator(0)])


class Bill(models.Model):
    PRICE_OF_FLIGHT = 9

    signup = models.OneToOneField(Signup, on_delete=models.CASCADE, related_name="bill")
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="bills")
    payed = models.SmallIntegerField(validators=[MinValueValidator(0)])

    class Meta:
        unique_together = (("signup", "report"),)

    def __str__(self):
        return f"{self.signup.pilot} for {self.report}"

    @property
    def details(self):
        """Compute details in one place, to keep database calls low"""
        runs = self.signup.runs.all()
        num_flights = len([run for run in runs if run.is_flight])
        num_services = len([run for run in runs if run.is_service])
        return {
            "num_flights": num_flights,
            "costs_flights": num_flights * self.PRICE_OF_FLIGHT,
            "num_services": num_services,
            "costs_services": -num_services * self.PRICE_OF_FLIGHT,
            "to_pay": (num_flights - num_services) * self.PRICE_OF_FLIGHT,
        }

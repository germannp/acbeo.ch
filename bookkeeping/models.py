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
    def revenue(self):
        bills = self.bills.all()
        return sum(bill.payed for bill in bills)

    @property
    def total_expenses(self):
        return sum(expense.amount for expense in self.expenses.all())

    @property
    def difference(self):
        if self.cash_at_end:
            return self.cash_at_end - (
                self.cash_at_start + self.revenue - self.total_expenses
            )

    @property
    def num_unpayed_signups(self):
        return len(
            [signup for signup in self.training.active_signups if signup.must_be_payed]
        )


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
    def num_flights(self):
        runs = self.signup.runs.all()
        return len([run for run in runs if run.is_flight])

    @property
    def costs_flights(self):
        return self.num_flights * self.PRICE_OF_FLIGHT

    @property
    def num_services(self):
        runs = self.signup.runs.all()
        return len([run for run in runs if run.is_service])

    @property
    def revenue_services(self):
        return self.num_services * self.PRICE_OF_FLIGHT

    @property
    def to_pay(self):
        purchases = self.signup.purchases.all()
        costs_purchases = sum(purchase.price for purchase in purchases)
        return self.costs_flights - self.revenue_services + costs_purchases


class Purchase(models.Model):
    class PRICES(models.IntegerChoices):
        # Must be of the form "DESCRIPTION, Fr. PRICE"
        REARMING_KIT = 0, "Patrone, Fr. 36"
        LIFEJACKET = 1, "Schwimmweste, Fr. 80"

    signup = models.ForeignKey(
        Signup, on_delete=models.CASCADE, related_name="purchases"
    )
    description = models.CharField(max_length=50)
    price = models.SmallIntegerField(validators=[MinValueValidator(0)])

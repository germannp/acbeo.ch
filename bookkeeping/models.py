from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.dispatch import receiver


class Report(models.Model):
    training = models.OneToOneField(
        "trainings.Training", on_delete=models.CASCADE, primary_key=True
    )
    cash_at_start = models.SmallIntegerField(validators=[MinValueValidator(0)])
    cash_at_end = models.SmallIntegerField(
        blank=True, null=True, validators=[MinValueValidator(0)]
    )
    orga_1 = models.ForeignKey(
        "trainings.Signup",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="reports_1",
    )
    orga_2 = models.ForeignKey(
        "trainings.Signup",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="reports_2",
    )
    remarks = models.CharField(max_length=300, default="", blank=True)

    def __str__(self):
        return f"{self.training}"

    @property
    def orgas(self):
        return [orga for orga in [self.orga_1, self.orga_2] if orga]

    @property
    def cash_revenue(self):
        bills = self.bills.all()
        return sum(bill.amount for bill in bills if bill.was_paid_in_cash)

    @property
    def other_revenue(self):
        bills = self.bills.all()
        return sum(bill.amount for bill in bills if not bill.was_paid_in_cash)

    @property
    def cash_expediture(self):
        expenses = sum(expense.amount for expense in self.expenses.all())
        absorptions = sum(absorption.amount for absorption in self.absorptions.all())
        return expenses + absorptions

    @property
    def difference(self):
        if self.cash_at_end:
            return self.cash_at_end - (
                self.cash_at_start + self.cash_revenue - self.cash_expediture
            )

    @property
    def num_unpaid_signups(self):
        return len(
            [signup for signup in self.training.active_signups if signup.must_be_paid]
        )


class Expense(models.Model):
    class Reasons(models.IntegerChoices):
        GAS = 0, "Tanken"
        PARKING = 1, "Parkkarte"
        STREET = 2, "Kleber Axalpstrasse"
        OTHER = 3, "Anderes (bitte angeben)"

    report = models.ForeignKey(
        Report, on_delete=models.CASCADE, related_name="expenses"
    )
    reason = models.CharField(max_length=50, blank=True)
    amount = models.SmallIntegerField(validators=[MinValueValidator(0)])

    @property
    def description(self):
        return self.reason


class PaymentMethods(models.IntegerChoices):
    CASH = 0, "Bar"
    BANK_TRANSFER = 1, "Überweisung"
    TWINT = 2, "TWINT"


class Absorption(models.Model):
    PAYMENT_CHOICES = [
        choice for choice in PaymentMethods.choices if choice[0] != PaymentMethods.CASH
    ]

    report = models.ForeignKey(
        Report, on_delete=models.CASCADE, related_name="absorptions"
    )
    signup = models.ForeignKey(
        "trainings.Signup", on_delete=models.CASCADE, related_name="absorptions"
    )
    reason = "Abschöpfung"
    amount = models.SmallIntegerField(validators=[MinValueValidator(0)])
    method = models.SmallIntegerField(choices=PAYMENT_CHOICES)

    @property
    def description(self):
        return f"Abschöpfung {self.signup.pilot}"


class Run(models.Model):
    Kind = models.IntegerChoices("Kind", "FLIGHT BREAK BUS BOAT")

    signup = models.ForeignKey(
        "trainings.Signup", on_delete=models.CASCADE, related_name="runs"
    )
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
        return self.kind != self.Kind.BREAK

    @property
    def is_flight(self):
        return self.kind == self.Kind.FLIGHT

    @property
    def is_service(self):
        return self.kind in (self.Kind.BUS, self.Kind.BOAT)

    def save(self, *args, **kwargs):
        if self.signup.is_paid:
            raise ValidationError(f"{self.signup.pilot} hat bereits bezahlt.")
        super().save(*args, **kwargs)


class Bill(models.Model):
    PRICE_OF_FLIGHT = 9
    PAYMENT_CHOICES = [
        choice
        for choice in PaymentMethods.choices
        if choice[0] != PaymentMethods.BANK_TRANSFER
    ]

    signup = models.OneToOneField(
        "trainings.Signup", on_delete=models.CASCADE, related_name="bill"
    )
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="bills")
    # Rather than handing money out, we add extra services to pilot.prepaid_flights,
    # thus bill.prepaid_flights can be negative.
    prepaid_flights = models.SmallIntegerField()
    amount = models.SmallIntegerField(validators=[MinValueValidator(0)])
    method = models.SmallIntegerField(choices=PAYMENT_CHOICES)

    class Meta:
        unique_together = (("signup", "report"),)

    def __str__(self):
        return f"Bill for {self.signup.pilot} on {self.signup.training}"

    @property
    def description(self):
        return f"Rechnung {self.signup.pilot}"

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
        num_services = len([run for run in runs if run.is_service])
        if self.signup.is_training_orga:
            num_services += 1
        return num_services

    @property
    def revenue_services(self):
        return self.num_services * self.PRICE_OF_FLIGHT

    @property
    def num_prepaid_flights(self):
        return min(
            self.num_flights - self.num_services, self.signup.pilot.prepaid_flights
        )

    @property
    def costs_prepaid_flights(self):
        return self.num_prepaid_flights * self.PRICE_OF_FLIGHT

    @property
    def num_flights_to_pay(self):
        return self.num_flights - self.num_services - self.num_prepaid_flights

    @property
    def costs_flights_to_pay(self):
        assert 0 <= self.num_flights_to_pay, f"Negative flights to pay in ({self})"
        return self.num_flights_to_pay * self.PRICE_OF_FLIGHT

    @property
    def to_pay(self):
        purchases = self.signup.purchases.all()
        costs_purchases = sum(purchase.price for purchase in purchases)
        return self.costs_flights_to_pay + costs_purchases

    @property
    def was_paid_in_cash(self):
        return self.method == PaymentMethods.CASH


@receiver(models.signals.post_save, sender=Bill)
def pay_with_prepaid_flights(sender, instance, created, **kwargs):
    if not created:
        return

    if not instance.prepaid_flights:
        return

    instance.signup.pilot.prepaid_flights -= instance.prepaid_flights
    instance.signup.pilot.save()


@receiver(models.signals.post_delete, sender=Bill)
def return_prepaid_flights(sender, instance, **kwargs):
    if not instance.prepaid_flights:
        return

    instance.signup.pilot.prepaid_flights += instance.prepaid_flights
    instance.signup.pilot.save()


class Purchase(models.Model):
    class Items(models.IntegerChoices):
        PREPAID_FLIGHTS = 0, "Abo (10 Flüge), Fr. 72"
        REARMING_KIT = 1, "Patrone, Fr. 36"
        LIFEJACKET = 2, "Schwimmweste, Fr. 80"

    DAY_PASS_DESCRIPTION = "Tagesmitgliedschaft"
    DAY_PASS_PRICE = 30

    signup = models.ForeignKey(
        "trainings.Signup", on_delete=models.CASCADE, related_name="purchases"
    )
    report = models.ForeignKey(
        Report, on_delete=models.CASCADE, related_name="purchases"
    )
    description = models.CharField(max_length=50)
    price = models.SmallIntegerField(validators=[MinValueValidator(0)])

    @classmethod
    def save_item(cls, signup, report, choice):
        assert not signup.is_paid, "Cannot save item for paid signup."
        description, price = cls.Items.choices[choice][1].split(", Fr. ")
        return cls.objects.create(
            signup=signup, report=report, description=description, price=int(price)
        )

    @classmethod
    def save_day_pass(cls, signup, report):
        assert not signup.is_paid, "Cannot save day pass for paid signup."
        return cls.objects.create(
            signup=signup,
            report=report,
            description=cls.DAY_PASS_DESCRIPTION,
            price=cls.DAY_PASS_PRICE,
        )

    @property
    def is_day_pass(self):
        return self.description == self.DAY_PASS_DESCRIPTION

    @property
    def is_prepaid_flights(self):
        return self.description in self.Items.PREPAID_FLIGHTS.label

    @property
    def is_equipment(self):
        return (
            self.description in self.Items.REARMING_KIT.label
            or self.description in self.Items.LIFEJACKET.label
        )


@receiver(models.signals.post_save, sender=Purchase)
def add_prepaid_flights(sender, instance, **kwargs):
    if instance.description in sender.Items.PREPAID_FLIGHTS.label:
        instance.signup.pilot.prepaid_flights += 10
        instance.signup.pilot.save()


@receiver(models.signals.post_delete, sender=Purchase)
def delete_prepaid_flights(sender, instance, **kwargs):
    if instance.description in sender.Items.PREPAID_FLIGHTS.label:
        instance.signup.pilot.prepaid_flights -= 10
        instance.signup.pilot.save()

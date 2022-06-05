from datetime import datetime

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils.timezone import make_aware
from django.utils.translation import gettext_lazy as _


class Training(models.Model):
    date = models.DateField(unique=True)
    max_pilots = models.PositiveSmallIntegerField(
        default=11,
        blank=False,
        null=False,
        validators=[MinValueValidator(6), MaxValueValidator(21)],
    )
    info = models.CharField(max_length=300, default="", blank=True)
    emergency_mail_sender = models.ForeignKey(
        User,
        on_delete=models.SET_DEFAULT,
        default=None,
        blank=True,
        null=True,
        db_index=False,
    )

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date}"

    def pilots(self):
        return [signup.pilot for signup in self.signups.all()]

    def select_signups(self):
        for signup in self.signups.all()[: self.max_pilots]:
            signup.select()


class Signup(models.Model):
    Status = models.IntegerChoices("Status", "Selected Waiting Canceled")

    pilot = models.ForeignKey(User, on_delete=models.CASCADE, related_name="signups")
    training = models.ForeignKey(
        Training, on_delete=models.CASCADE, related_name="signups"
    )
    status = models.IntegerField(choices=Status.choices, default=Status.Waiting)
    signed_up_on = models.DateTimeField(auto_now_add=True)
    is_certain = models.BooleanField(default=True)
    comment = models.CharField(max_length=150, default="", blank=True)

    class Meta:
        unique_together = (("pilot", "training"),)
        ordering = ["status", "signed_up_on"]

    def __str__(self):
        return f"{self.pilot} for {self.training}"

    def select(self):
        if self.status != self.Status.Waiting:
            return
        self.status = self.Status.Selected
        self.save()

    def cancel(self):
        self.status = self.Status.Canceled
        # Not saving, because called before saving updates from form

    def resignup(self):
        self.signed_up_on = make_aware(datetime.now())
        self.status = self.Status.Waiting
        # Not saving, because called before saving updates from form

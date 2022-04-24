from datetime import datetime

from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import make_aware
from django.utils.translation import gettext_lazy as _


class Training(models.Model):
    date = models.DateField(unique=True)
    info = models.CharField(max_length=300, default="", blank=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date}"


class Signup(models.Model):
    Status = models.IntegerChoices("Status", "Selected Waiting Canceled")

    pilot = models.ForeignKey(User, on_delete=models.CASCADE, related_name="signups")
    training = models.ForeignKey(
        Training, on_delete=models.CASCADE, related_name="signups"
    )
    status = models.IntegerField(choices=Status.choices, default=Status.Waiting)
    comment = models.CharField(max_length=150, default="", blank=True)
    signed_up_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("pilot", "training"),)
        ordering = ["status", "signed_up_on"]

    def __str__(self):
        return f"{self.pilot} for {self.training}"

    def cancel(self):
        self.status = self.Status.Canceled

    def resignup(self):
        self.signed_up_on = make_aware(datetime.now())
        self.status = self.Status.Waiting

from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _


class Training(models.Model):
    date = models.DateField(unique=True)
    info = models.CharField(max_length=300, default="", blank=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date}"


class Singup(models.Model):
    class Status(models.TextChoices):
        WAIT = "🟡", _("Wait")
        SELECTED = "🟢", _("Selected")
        CANCELED = "❌", _("Canceled")

    pilot = models.ForeignKey(User, on_delete=models.CASCADE, related_name="signups")
    training = models.ForeignKey(
        Training, on_delete=models.CASCADE, related_name="signups"
    )
    status = models.CharField(max_length=1, choices=Status.choices, default=Status.WAIT)
    comment = models.CharField(max_length=150, default="", blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("pilot", "training"),)

    def __str__(self):
        return f"{self.pilot} for {self.training}"

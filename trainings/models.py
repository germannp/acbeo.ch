from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _


class Registration(models.Model):
    class Status(models.TextChoices):
        WAIT = "WAIT", _("Wait")
        SELECTED = "SELE", _("Selected")
        CANCELED = "CANC", _("Canceled")

    pilot = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="registrations"
    )
    date = models.DateField()
    status = models.CharField(
        max_length=4,
        choices=Status.choices,
        default=Status.WAIT,
    )
    comment = models.CharField(max_length=200, default=None, blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("pilot", "date"),)
        ordering = ["date", "pilot"]

    def __str__(self):
        return f"{self.pilot} on {self.date}"

from datetime import date, datetime

from django.conf import settings
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
    min_orgas = 2
    priority_date = models.DateField(
        default=datetime.fromisoformat("2010-04-09").date()
    )
    info = models.CharField(max_length=300, default="", blank=True)
    emergency_mail_sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
        signups = self.signups.all()

        selected_orgas = [signup for signup in signups if signup.is_selected_orga]
        spots_for_orgas = max(0, self.min_orgas - len(selected_orgas))
        if spots_for_orgas:
            waiting_orgas = [signup for signup in signups if signup.is_waiting_orga]
            orgas_to_select = waiting_orgas[:spots_for_orgas]
            signups = orgas_to_select + [
                signup for signup in signups if signup not in orgas_to_select
            ]
            spots_for_orgas -= len(orgas_to_select)

        if date.today() <= self.priority_date:
            signups = [signup for signup in signups if signup.has_priority]

        for signup in signups[: self.max_pilots - spots_for_orgas]:
            signup.select()


class Signup(models.Model):
    Status = models.IntegerChoices("Status", "Selected Waiting Canceled")
    Time = models.IntegerChoices("Time", "WholeDay ArriveLate LeaveEarly Individually")

    pilot = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="signups"
    )
    training = models.ForeignKey(
        Training, on_delete=models.CASCADE, related_name="signups"
    )
    status = models.SmallIntegerField(choices=Status.choices, default=Status.Waiting)
    signed_up_on = models.DateTimeField(auto_now_add=True)
    is_certain = models.BooleanField(default=True)
    for_time = models.SmallIntegerField(choices=Time.choices, default=Time.WholeDay)
    for_sketchy_weather = models.BooleanField(default=True)
    comment = models.CharField(max_length=150, default="", blank=True)

    class Meta:
        unique_together = (("pilot", "training"),)
        ordering = ["status", "signed_up_on"]

    def __str__(self):
        return f"{self.pilot} {self.get_status_display()} for {self.training}"

    @property
    def has_priority(self):
        return (
            self.pilot.is_member
            and self.is_certain
            and self.for_time == self.Time.WholeDay
        )

    @property
    def is_selected_orga(self):
        return self.status == self.Status.Selected and self.pilot.is_orga

    @property
    def is_waiting_orga(self):
        return self.status == self.Status.Waiting and self.pilot.is_orga

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

    def update_is_certain(self, new_is_certain):
        if self.is_certain == new_is_certain:
            return
        self.is_certain = new_is_certain
        if new_is_certain:
            return
        self.signed_up_on = make_aware(datetime.now())
        self.status = self.Status.Waiting
        # Not saving, because called before saving updates from form

    def update_for_time(self, new_for_time):
        if self.for_time == new_for_time:
            return
        old_for_time, self.for_time = self.for_time, new_for_time
        if new_for_time == self.Time.WholeDay:
            return
        if old_for_time != self.Time.WholeDay:
            return
        self.signed_up_on = make_aware(datetime.now())
        self.status = self.Status.Waiting
        # Not saving, because called before saving updates from form

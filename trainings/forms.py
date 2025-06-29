from datetime import date, timedelta

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import strip_tags
from .models import Training, Signup


def date_relative_to_next_august(month, day):
    today = timezone.now().date()
    year_of_next_august = today.year + (8 <= today.month)
    return date(year_of_next_august, month, day)


class TrainingCreateForm(forms.Form):
    first_day = forms.DateField(initial=lambda: date_relative_to_next_august(8, 1))
    last_day = forms.DateField(initial=lambda: date_relative_to_next_august(8, 31))
    priority_date = forms.DateField(initial=lambda: date_relative_to_next_august(4, 15))
    max_pilots = forms.IntegerField(
        initial=11, validators=[MinValueValidator(6), MaxValueValidator(33)]
    )
    info = forms.CharField(max_length=300, initial="Axalpwochen")

    def clean_first_day(self):
        first_day = self.cleaned_data["first_day"]
        if first_day < timezone.now().date():
            raise ValidationError(
                "Es können keine Trainings in der Vergangenheit erstellt werden."
            )
        return first_day

    def clean_last_day(self):
        last_day = self.cleaned_data["last_day"]
        if last_day > timezone.now().date() + timedelta(days=365):
            raise ValidationError(
                "Trainings können höchstens ein Jahr im Voraus erstellt werden."
            )
        return last_day

    def clean(self):
        cleaned_data = super().clean()
        first_day = cleaned_data.get("first_day")
        last_day = cleaned_data.get("last_day")
        if not (first_day and last_day):
            return

        if first_day > last_day:
            raise ValidationError("Der erste Tag muss vor dem Letzten liegen.")

        if last_day - first_day > timedelta(days=31):
            raise ValidationError(
                "Es können höchstens 31 Trainings auf einmal erstellt werden."
            )

        priority_date = cleaned_data.get("priority_date")
        if not (priority_date and last_day):
            return

        if priority_date > last_day:
            raise ValidationError(
                "Das Vorrang-Datum kann nicht nach dem letzten Tag sein."
            )

    def create_trainings(self):
        day = self.cleaned_data["first_day"]
        while day <= self.cleaned_data["last_day"]:
            if Training.objects.filter(date=day).exists():
                training = Training.objects.get(date=day)
            else:
                training = Training(date=day)
            training.info = self.cleaned_data["info"]
            training.max_pilots = self.cleaned_data["max_pilots"]
            training.priority_date = self.cleaned_data["priority_date"]
            training.save()
            day += timedelta(days=1)


class TrainingUpdateForm(forms.ModelForm):
    class Meta:
        model = Training
        exclude = ("date", "emergency_mail_sender")

    def clean(self):
        cleaned_data = super().clean()
        priority_date = cleaned_data.get("priority_date")
        if not priority_date:
            return

        if priority_date > self.instance.date:
            raise ValidationError(
                "Das Vorrang-Datum kann nicht nach dem Training sein."
            )


class EmergencyMailForm(forms.ModelForm):
    Start = models.IntegerChoices("Start", "8:00 8:30 9:00 9:30 10:00 10:30 11:00")
    End = models.IntegerChoices("End", "16:00 17:00 18:00 19:00 20:00")

    class EmergencyContactChoiceField(forms.ModelMultipleChoiceField):
        def label_from_instance(self, signup):
            return f"{signup.pilot}, {signup.pilot.phone}"

    start = forms.ChoiceField(choices=Start.choices, initial=Start["9:00"])
    end = forms.ChoiceField(choices=End.choices, initial=End["19:00"])
    emergency_contacts = EmergencyContactChoiceField(
        queryset=None, widget=forms.CheckboxSelectMultiple, required=False
    )
    ctr_inactive = forms.BooleanField(required=False)

    class Meta:
        model = Training
        fields = tuple()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["emergency_contacts"].queryset = self.instance.signups.filter(
            status=Signup.Status.SELECTED
        ).select_related("pilot")

    def clean_emergency_contacts(self):
        emergency_contacts = self.cleaned_data["emergency_contacts"]
        if len(emergency_contacts) != 2:
            raise ValidationError("Bitte genau zwei Notfallkontakte auswählen.")
        return emergency_contacts

    def clean_ctr_inactive(self):
        ctr_inactive = self.cleaned_data["ctr_inactive"]
        if not ctr_inactive:
            raise ValidationError(
                "Wir dürfen nur mit Absprache fliegen, wenn CTR/TMA Meiringen aktiv ist."
            )
        return ctr_inactive

    def send_mail(self):
        date = date_format(self.instance.date, "l, j. F")
        start = self.Start(int(self.cleaned_data["start"])).label
        end = self.End(int(self.cleaned_data["end"])).label
        contacts = self.cleaned_data["emergency_contacts"]
        # fmt: off
        html_message = (
            "<b>Was</b>: Information über Gleitschirm Sicherheitstraining über dem "
            "Brienzersee<br>\n<br>\n"

            "<b>Wo</b>: Östliches Seebecken Brienzersee<br>\n"
            "Start: Axalp<br>\n"
            "Landung: Aaregg, Forsthaus<br>\n<br>\n"

            "<b>Zweck</b>: Unter den entsprechenden Sicherheitsvorkehrungen werden "
            "verschiedene Extremflugsituationen geübt. Wasserlandungen sind "
            "nicht vorgesehen, aber jederzeit möglich. Ein eigenes, bemanntes "
            "Boot steht für alle Fälle auf dem See bereit.<br>\n<br>\n"

            f"<b>Wann</b>: {date} von {start} bis {end} (falls das Wetter passt).<br>\n<br>\n"

            "<b>Veranstalter</b>: Acro Club Berner Oberland, acbeo.ch.<br>\n<br>\n"

            f"<b>Ansprechpersonen</b>:<br>\n"
            f"{contacts[0].pilot}, {contacts[0].pilot.phone}<br>\n"
            f"{contacts[1].pilot}, {contacts[1].pilot.phone}<br>\n<br>\n"

            "Mit freundlichen Grüssen<br>\n"
            f"{self.sender}<br>\n"
        )
        # fmt: on
        send_mail(
            subject=f"{date}: Gleitschirm-Sicherheitstraining ueber dem Brienzersee",
            message=strip_tags(html_message),
            html_message=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=settings.EMERGENCY_EMAILS + [self.sender.email],
            fail_silently=False,
        )
        self.instance.emergency_mail_sender = self.sender


class SignupCreateForm(forms.ModelForm):
    date = forms.DateField()

    class Meta:
        model = Signup
        exclude = ("pilot", "training", "status")

    def clean_date(self):
        training_date = self.cleaned_data["date"]
        today = timezone.now().date()
        if training_date < today:
            raise ValidationError(
                "Einschreiben ist nur für kommende Trainings möglich."
            )
        if training_date > today + timedelta(days=365):
            raise ValidationError(
                "Einschreiben ist höchstens ein Jahr im Voraus möglich."
            )
        return training_date


class SignupUpdateForm(forms.ModelForm):
    class Meta:
        model = Signup
        exclude = ("pilot", "training", "status")

    def clean(self):
        cleaned_data = super().clean()
        self.instance.update_is_certain(cleaned_data["is_certain"])
        self.instance.update_duration(cleaned_data["duration"])

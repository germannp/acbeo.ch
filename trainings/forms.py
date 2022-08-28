import datetime

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils.html import strip_tags

from .models import Training, Signup


def date_relative_to_next_august(month, day):
    today = datetime.date.today()
    year_of_next_august = today.year + (8 <= today.month)
    return datetime.date(year_of_next_august, month, day)


class TrainingCreateForm(forms.Form):
    first_day = forms.DateField(initial=lambda: date_relative_to_next_august(8, 1))
    last_day = forms.DateField(initial=lambda: date_relative_to_next_august(8, 31))
    priority_date = forms.DateField(initial=lambda: date_relative_to_next_august(4, 15))
    max_pilots = forms.IntegerField(
        initial=10, validators=[MinValueValidator(6), MaxValueValidator(21)]
    )
    info = forms.CharField(max_length=300, initial="Axalpwochen")

    def clean_first_day(self):
        first_day = self.cleaned_data["first_day"]
        if first_day < datetime.date.today():
            raise ValidationError(
                "Es können keine Trainings in der Vergangenheit erstellt werden."
            )
        return first_day

    def clean_last_day(self):
        last_day = self.cleaned_data["last_day"]
        if last_day > datetime.date.today() + datetime.timedelta(days=365):
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

        if last_day - first_day > datetime.timedelta(days=31):
            raise ValidationError(
                "Es können höchstens 31 Trainings auf einmal erstellt werden."
            )
        
        priority_date = cleaned_data.get("priority_date")
        if not (priority_date and last_day):
            return

        if priority_date > last_day:
            raise ValidationError("Das Vorrang-Datum kann nicht nach dem letzten Tag sein.")


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
            day += datetime.timedelta(days=1)


class TrainingUpdateForm(forms.ModelForm):
    class Meta:
        model = Training
        exclude = ["date", "emergency_mail_sender"]

    def clean(self):
        cleaned_data = super().clean()
        priority_date = cleaned_data.get("priority_date")
        if not priority_date:
            return

        if priority_date > self.instance.date:
            raise ValidationError("Das Vorrang-Datum kann nicht nach dem Training sein.")


class EmergencyMailForm(forms.ModelForm):
    Start = models.IntegerChoices("Start", "8:00 8:30 9:00 9:30 10:00 10:30 11:00")
    End = models.IntegerChoices("End", "16:00 17:00 18:00 19:00 20:00")

    class EmergencyContactChoiceField(forms.ModelMultipleChoiceField):
        def label_from_instance(self, signup):
            return f"{signup.pilot}, {signup.pilot.phone}"

    start = forms.ChoiceField(choices=Start.choices, initial=Start["9:00"])
    end = forms.ChoiceField(choices=End.choices, initial=End["19:00"])
    emergency_contacts = EmergencyContactChoiceField(
        queryset=None, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Training
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["emergency_contacts"].queryset = self.instance.signups.filter(
            status=Signup.Status.Selected
        ).select_related("pilot")

    def clean_emergency_contacts(self):
        emergency_contacts = self.cleaned_data["emergency_contacts"]
        if len(emergency_contacts) != 2:
            raise ValidationError("Bitte genau zwei Notfallkontakte ausgewählen.")
        return emergency_contacts

    def send_mail(self):
        date = self.instance.date.strftime("%A, %d. %B").replace(" 0", " ")
        start = self.Start(int(self.cleaned_data["start"])).label
        end = self.End(int(self.cleaned_data["end"])).label
        contacts = self.cleaned_data["emergency_contacts"]
        # fmt: off
        html_message = (
            "<b>Was</b>: Information über Gleitschirm Sicherheitstraining über dem "
            "Brienzersee\n\n"

            "<b>Geht an</b>: Einsatzzentrale der Kantonspolizei in Thun. Bitte weiterleiten "
            "an die Polizeiwachen Brienz und Meiringen, und die Seepolizei Brienzersee.\n\n"

            "<b>Wo</b>: Östliches Seebecken Brienzersee\n"
            "Start: Axalp\n"
            "Landung: Aaregg, Forsthaus\n\n"

            "<b>Zweck</b>: Unter den entsprechenden Sicherheitsvorkehrungen werden "
            "verschiedene Extremflugsituationen geübt. Wasserlandungen sind "
            "nicht vorgesehen, aber jederzeit möglich. Ein eigenes, bemanntes "
            "Boot steht für alle Fälle auf dem See bereit.\n\n"

            f"<b>Wann</b>: {date} von {start} bis {end} (falls das Wetter passt).\n\n"

            "<b>Veranstalter</b>: Acro Club Berner Oberland, acbeo.ch.\n\n"

            f"<b>Ansprechpersonen</b>:\n"
            f"{contacts[0]}, {contacts[0].pilot.phone}\n"
            f"{contacts[1]}, {contacts[1].pilot.phone}\n\n"

            "Mit freundlichen Grüssen\n"
            f"{self.sender.first_name} {self.sender.last_name}\n"
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
        exclude = ["pilot", "training", "status"]

    def clean_date(self):
        date = self.cleaned_data["date"]
        today = datetime.date.today()
        if date < today:
            raise ValidationError(
                "Einschreiben ist nur für kommende Trainings möglich."
            )
        if date > today + datetime.timedelta(days=365):
            raise ValidationError(
                "Einschreiben ist höchstens ein Jahr im Voraus möglich."
            )
        return date


class SignupUpdateForm(forms.ModelForm):
    class Meta:
        model = Signup
        exclude = ["pilot", "training", "status"]

    def clean(self):
        cleaned_data = super().clean()
        self.instance.update_is_certain(cleaned_data["is_certain"])
        self.instance.update_for_time(cleaned_data["for_time"])

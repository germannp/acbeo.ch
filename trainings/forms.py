import locale

from django import forms
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import models
from django.utils.html import strip_tags

from .models import Training, Signup

locale.setlocale(locale.LC_TIME, "de_CH")


class TrainingUpdateForm(forms.ModelForm):
    class Meta:
        model = Training
        fields = ["info", "max_pilots"]


class EmergencyMailForm(forms.ModelForm):
    Start = models.IntegerChoices("Start", "8:00 8:30 9:00 9:30 10:00 10:30 11:00")
    End = models.IntegerChoices("End", "16:00 17:00 18:00 19:00 20:00")

    class EmergencyContactChoiceField(forms.ModelMultipleChoiceField):
        def label_from_instance(self, signup):
            return f"{signup.pilot.first_name} {signup.pilot.last_name }"

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
            f"{contacts[0].pilot.first_name} {contacts[0].pilot.last_name}\n"
            f"{contacts[1].pilot.first_name} {contacts[1].pilot.last_name}\n\n"

            "Mit freundlichen Grüssen\n"
            f"{self.sender.first_name} {self.sender.last_name}\n"
        )
        # fmt: on
        send_mail(
            subject=f"{date}: Gleitschirm-Sicherheitstraining ueber dem Brienzersee",
            message=strip_tags(html_message),
            html_message=html_message,
            from_email="info@example.com",
            recipient_list=["emergency@example.com", self.sender.email],
            fail_silently=False,
        )
        self.instance.emergency_mail_sender = self.sender


class SignupCreateForm(forms.ModelForm):
    class Meta:
        model = Signup
        exclude = ["pilot", "training", "status"]


class SignupUpdateForm(forms.ModelForm):
    class Meta:
        model = Signup
        exclude = ["pilot", "training", "status"]

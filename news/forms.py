from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail

from .models import Pilot


class ContactForm(forms.Form):
    email = forms.EmailField(required=True)
    subject = forms.CharField(required=True)
    message = forms.CharField(required=True)

    def send_mail(self):
        send_mail(
            subject="Kontaktformular: " + self.cleaned_data["subject"],
            message=self.cleaned_data["message"],
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.INFO_EMAIL, self.cleaned_data["email"]],
            fail_silently=False,
        )


class MembershipForm(forms.Form):
    street = forms.CharField(required=True)
    town = forms.CharField(required=True)
    country = forms.CharField(required=True)
    request_membership = forms.BooleanField(required=False)
    accept_statutes = forms.BooleanField(required=False)
    comment = forms.CharField(required=False)

    def clean_request_membership(self):
        request_membership = self.cleaned_data.get("request_membership")
        if not request_membership:
            raise ValidationError("Du musst Mitglied werden wollen.")
        return request_membership

    def clean_accept_statutes(self):
        accept_statutes = self.cleaned_data.get("accept_statutes")
        if not accept_statutes:
            raise ValidationError("Du musst mit unseren Statuten einverstanden sein.")
        return accept_statutes

    def send_mail(self):
        message = "\n".join(
            [
                str(self.sender),
                self.cleaned_data["street"],
                self.cleaned_data["town"],
                self.cleaned_data["country"],
                self.sender.email,
                self.sender.phone,
                "\nMöchte Mitglied werden.",
            ]
        )
        if comment := self.cleaned_data["comment"]:
            message += "\n\nKommentar:\n" + comment
        send_mail(
            subject="Antrag ACBeo-Mitgliedschaft",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.INFO_EMAIL, self.sender.email],
            fail_silently=False,
        )


class PilotCreationForm(forms.ModelForm):
    accept_safety_concept = forms.BooleanField(required=False)
    password1 = forms.CharField()
    password2 = forms.CharField()
    recaptcha = forms.CharField(required=False)

    class Meta:
        model = Pilot
        fields = ("first_name", "last_name", "email", "phone")

    def clean_accept_safety_concept(self):
        accept_safety_concept = self.cleaned_data.get("accept_safety_concept")
        if not accept_safety_concept:
            raise ValidationError(
                "Du musst mit unserem Sicherheitskonzept einverstanden sein."
            )
        return accept_safety_concept

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError("Passwörter müssen gleich sein.")
        return password2

    def save(self, commit=True):
        pilot = super().save(commit=False)
        pilot.set_password(self.cleaned_data["password1"])
        if commit:
            pilot.save()
        return pilot


class PilotUpdateForm(forms.ModelForm):
    class Meta:
        model = Pilot
        fields = ("first_name", "last_name", "email", "phone")

    def send_mail(self):
        if not self.changed_data:
            return

        message = (
            f"{self.cleaned_data['first_name']} {self.cleaned_data['last_name']} hat "
            "folgende Änderungen am Konto gemacht:\n\n"
        )
        for field in self.changed_data:
            message += f"{field}: {self[field].initial} -> {self.cleaned_data[field]}\n"
        send_mail(
            subject="Änderung an Konto",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.INFO_EMAIL],
            fail_silently=False,
        )

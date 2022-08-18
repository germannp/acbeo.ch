from django import forms
from django.core.exceptions import ValidationError
from django.core.mail import send_mail

from .models import Pilot


class ContactForm(forms.Form):
    email = forms.EmailField(required=True)
    subject = forms.CharField(required=True)
    message = forms.CharField(required=True)

    def send_mail(self):
        send_mail(
            subject=self.cleaned_data["subject"],
            message=self.cleaned_data["message"],
            from_email=self.cleaned_data["email"],
            recipient_list=["info@example.com"],
            fail_silently=False,
        )


class MembershipForm(forms.Form):
    accept_statutes = forms.BooleanField(required=False)
    comment = forms.CharField(required=False)

    def clean_accept_statutes(self):
        accept_statutes = self.cleaned_data.get("accept_statutes")
        if not accept_statutes:
            raise ValidationError("Du musst mit unseren Statuten einverstanden sein.")
        return accept_statutes

    def send_mail(self):
        message = (
            f"{self.sender} möchte Mitglied werden. Die "
            f"Email ist {self.sender.email} und die Telefonnummer {self.sender.phone}."
        )
        comment = self.cleaned_data["comment"]
        if comment:
            message += "\n\nKommentar:\n" + comment
        send_mail(
            subject="Antrag ACBeo-Mitgliedschaft",
            message=message,
            from_email=self.sender.email,
            recipient_list=["info@example.com", self.sender.email],
            fail_silently=False,
        )


class PilotCreationForm(forms.ModelForm):
    accept_safety_concept = forms.BooleanField(required=False)
    password1 = forms.CharField()
    password2 = forms.CharField()

    class Meta:
        model = Pilot
        fields = ("first_name", "last_name", "email", "phone")

    def clean_accept_safety_concept(self):
        accept_safety_concept = self.cleaned_data.get("accept_safety_concept")
        if not accept_safety_concept:
            raise ValidationError("Du musst mit unserem Sicherheitskonzept einverstanden sein.")
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

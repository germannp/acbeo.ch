from django import forms
from django.core.exceptions import ValidationError
from django.core.mail import send_mail

from .models import Pilot


class ContactForm(forms.Form):
    email = forms.EmailField(required=True)
    subject = forms.CharField(required=True)
    message = forms.CharField(widget=forms.Textarea, required=True)

    def send_mail(self):
        send_mail(
            subject=self.cleaned_data["subject"],
            message=self.cleaned_data["message"],
            from_email=self.cleaned_data["email"],
            recipient_list=["to@example.com"],
            fail_silently=False,
        )


class PilotCreationForm(forms.ModelForm):
    password1 = forms.CharField()
    password2 = forms.CharField()

    class Meta:
        model = Pilot
        fields = ("first_name", "last_name", "email", "phone")

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError("Passwords don't match")
        return password2

    def save(self, commit=True):
        pilot = super().save(commit=False)
        pilot.set_password(self.cleaned_data["password1"])
        if commit:
            pilot.save()
        return pilot

from django import forms

from . import models


class SignupForm(forms.ModelForm):
    class Meta:
        model = models.Registration
        exclude = ["pilot", "status"]


class UpdateForm(forms.ModelForm):
    class Meta:
        model = models.Registration
        exclude = ["pilot", "date", "status"]

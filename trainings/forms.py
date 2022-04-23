from django import forms

from . import models


class SignupForm(forms.ModelForm):
    date = forms.DateField()

    class Meta:
        model = models.Singup
        exclude = ["pilot", "training", "status"]


class UpdateForm(forms.ModelForm):
    class Meta:
        model = models.Singup
        exclude = ["pilot", "training", "status"]

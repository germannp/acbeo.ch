from django import forms

from . import models


class TrainingUpdateForm(forms.ModelForm):
    class Meta:
        model = models.Training
        exclude = ["date", "max_pilots"]


class SignupCreateForm(forms.ModelForm):
    class Meta:
        model = models.Signup
        exclude = ["pilot", "training", "status"]


class SignupUpdateForm(forms.ModelForm):
    class Meta:
        model = models.Signup
        exclude = ["pilot", "training", "status"]

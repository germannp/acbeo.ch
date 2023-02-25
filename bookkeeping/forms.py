from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.forms import modelformset_factory

from .models import Expense, Run, Purchase


class BaseRunFormSet(forms.BaseModelFormSet):
    model = Run

    def clean(self):
        if any(self.errors):
            # Don't bother validating the formset unless each form is valid on its own
            return

        num_buses = sum(form.instance.kind == Run.Kind.Bus for form in self.forms)
        if num_buses > 1:
            raise ValidationError("Höchstens eine Person kann Bus fahren.")

        num_boats = sum(form.instance.kind == Run.Kind.Boat for form in self.forms)
        if num_boats > 2:
            raise ValidationError("Höchstens zwei Personen können Boot machen.")


RunFormset = modelformset_factory(
    Run, fields=("kind",), formset=BaseRunFormSet, extra=0
)


class ExpenseCreateForm(forms.ModelForm):
    reason = forms.ChoiceField(
        choices=Expense.REASONS.choices,
        initial=Expense.REASONS.GAS,
        widget=forms.widgets.RadioSelect(attrs={"class": "form-check-input"}),
    )
    other_reason = forms.CharField(max_length=50, required=False)

    class Meta:
        model = Expense  # Allow view to fill in report
        fields = ("amount",)

    def clean(self):
        cleaned_data = super().clean()
        if (reason := int(cleaned_data.get("reason"))) != Expense.REASONS.OTHER:
            self.instance.reason = Expense.REASONS.choices[reason][1]
            return

        if not (other_reason := cleaned_data.get("other_reason")):
            raise ValidationError("Bitte Grund angeben.")
        self.instance.reason = other_reason


class PurchaseCrateForm(forms.ModelForm):
    item = forms.ChoiceField(
        choices=Purchase.ITEMS.choices,
        initial=Purchase.ITEMS.PREPAID_FLIGHTS,
        widget=forms.widgets.RadioSelect(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Purchase  # Allow view to fill in signup and report
        fields = ("item",)

    def create_purchase(self):
        Purchase.save_item(
            self.instance.signup, self.instance.report, int(self.cleaned_data["item"])
        )

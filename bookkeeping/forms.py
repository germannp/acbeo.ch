from django.forms import modelformset_factory
from django.core.exceptions import ValidationError
from django import forms

from .models import Run


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
    Run, fields=("kind",), formset=BaseRunFormSet, extra=30
)
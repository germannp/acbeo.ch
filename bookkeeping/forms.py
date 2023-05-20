from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.forms import modelformset_factory

from .models import Absorption, Bill, Expense, PaymentMethods, Purchase, Run
from trainings.models import Signup


class ExpenseCreateForm(forms.ModelForm):
    reason = forms.ChoiceField(
        choices=Expense.Reasons.choices,
        initial=Expense.Reasons.GAS,
        widget=forms.widgets.RadioSelect(attrs={"class": "form-check-input"}),
    )
    other_reason = forms.CharField(max_length=50, required=False)
    receipt = forms.FileField()

    class Meta:
        model = Expense  # Allow view to fill in report
        fields = ("amount",)

    def clean(self):
        cleaned_data = super().clean()
        if (reason := int(cleaned_data.get("reason"))) != Expense.Reasons.OTHER:
            self.instance.reason = Expense.Reasons.choices[reason][1]
            return

        if not (other_reason := cleaned_data.get("other_reason")):
            raise ValidationError("Bitte Grund angeben.")
        self.instance.reason = other_reason

    def send_mail(self):
        mail = EmailMessage(
            subject=f"Beleg für {self.instance.reason} über Fr. {self.instance.amount}",
            body=f"Erfasst von {self.sender} für das Training vom {self.instance.report.training.date}.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.FINANCE_EMAIL],
        )
        receipt = self.cleaned_data["receipt"]
        mail.attach(receipt.name, receipt.read(), receipt.content_type)
        mail.send(fail_silently=False)


class AbsorptionForm(forms.ModelForm):
    class SignupChoiceField(forms.ModelChoiceField):
        def label_from_instance(self, signup):
            return signup.pilot

    signup = SignupChoiceField(
        queryset=Signup.objects,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )
    method = forms.ChoiceField(
        choices=Absorption.PAYMENT_CHOICES,
        initial=PaymentMethods.BANK_TRANSFER,
        widget=forms.widgets.RadioSelect(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Absorption
        fields = ("signup", "amount", "method")


class BaseRunFormSet(forms.BaseModelFormSet):
    model = Run

    def clean(self):
        if any(self.errors):
            # Don't bother validating the formset unless each form is valid on its own
            return

        num_buses = sum(form.instance.kind == Run.Kind.BUS for form in self.forms)
        if num_buses > 1:
            raise ValidationError("Höchstens eine Person kann Bus fahren.")

        num_boats = sum(form.instance.kind == Run.Kind.BOAT for form in self.forms)
        if num_boats > 2:
            raise ValidationError("Höchstens zwei Personen können Boot machen.")


RunFormset = modelformset_factory(
    Run, fields=("kind",), formset=BaseRunFormSet, extra=0
)


class BillForm(forms.ModelForm):
    method = forms.ChoiceField(
        choices=Bill.PAYMENT_CHOICES,
        initial=PaymentMethods.CASH,
        widget=forms.widgets.RadioSelect(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Bill
        exclude = ("signup", "report")


class PurchaseCreateForm(forms.ModelForm):
    item = forms.ChoiceField(
        choices=Purchase.Items.choices,
        initial=Purchase.Items.PREPAID_FLIGHTS,
        widget=forms.widgets.RadioSelect(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Purchase  # Allow view to fill in signup and report
        fields = ("item",)

    def create_purchase(self):
        Purchase.save_item(
            self.instance.signup, self.instance.report, int(self.cleaned_data["item"])
        )

from datetime import timedelta
from http import HTTPStatus
from random import randint
import locale

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Absorption, PaymentMethods, Report
from trainings.models import Signup, Training


locale.setlocale(locale.LC_TIME, "de_CH")

TODAY = timezone.now().date()
YESTERDAY = TODAY - timedelta(days=1)


class AbsorptionCreateViewTests(TestCase):
    def setUp(self):
        self.guest = get_user_model().objects.create(
            email="guest@example.com", first_name="Guest"
        )
        self.orga = get_user_model().objects.create(
            email="orga@example.com", first_name="Orga", role=get_user_model().Role.ORGA
        )
        self.client.force_login(self.orga)

        training = Training.objects.create(date=TODAY)
        self.report = Report.objects.create(training=training, cash_at_start=1337)
        Signup(training=training, pilot=self.guest).save()
        self.signup = Signup.objects.create(training=training, pilot=self.orga)
        training.select_signups()

    def test_orga_required_to_see(self):
        self.client.force_login(self.guest)
        response = self.client.get(reverse("create_absorption", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_date_shown_and_signups_listed(self):
        response = self.client.get(reverse("create_absorption", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/absorption_create.html")
        self.assertContains(response, TODAY.strftime("%A, %d. %B").replace(" 0", " "))
        self.assertContains(response, self.guest)
        self.assertContains(response, self.orga)
        self.assertContains(
            response,
            f'value="{self.signup.pk}" class="form-check-input" id="id_signup_1" required checked',
        )
        self.assertContains(
            response,
            f'value="{PaymentMethods.BANK_TRANSFER}" class="form-check-input" id="id_method_0" required checked',
        )
        self.assertNotContains(response, PaymentMethods.CASH.label)

    def test_amount_cannot_be_negative_and_is_prefilled(self):
        amount = -42
        response = self.client.post(
            reverse("create_absorption", kwargs={"date": TODAY}),
            data={
                "signup": self.signup.pk,
                "amount": amount,
                "method": PaymentMethods.BANK_TRANSFER,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/absorption_create.html")
        self.assertContains(response, amount)

    def test_create_absorption(self):
        amount = 42
        response = self.client.post(
            reverse("create_absorption", kwargs={"date": TODAY}),
            data={
                "signup": self.signup.pk,
                "amount": amount,
                "method": PaymentMethods.BANK_TRANSFER,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(
            response,
            f"Abschöpfung von {self.signup.pilot} über Fr. {amount} gespeichert.",
        )
        self.assertEqual(1, len(Absorption.objects.all()))
        created_absorption = Absorption.objects.first()
        self.assertEqual(self.signup, created_absorption.signup)
        self.assertEqual(amount, created_absorption.amount)
        self.assertEqual(PaymentMethods.BANK_TRANSFER, created_absorption.method)

    def test_report_not_found_404(self):
        response = self.client.get(
            reverse("create_absorption", kwargs={"date": YESTERDAY})
        )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")


class AbsorptionUpdateViewTests(TestCase):
    def setUp(self):
        self.guest = get_user_model().objects.create(
            email="guest@example.com", first_name="Guest"
        )
        self.orga = get_user_model().objects.create(
            email="orga@example.com", first_name="Orga", role=get_user_model().Role.ORGA
        )
        self.client.force_login(self.orga)

        training = Training.objects.create(date=TODAY)
        self.report = Report.objects.create(training=training, cash_at_start=1337)
        Signup(training=training, pilot=self.guest).save()
        self.signup = Signup.objects.create(training=training, pilot=self.orga)
        self.absorption = Absorption.objects.create(
            report=self.report,
            signup=self.signup,
            amount=42,
            method=PaymentMethods.BANK_TRANSFER,
        )
        training.select_signups()

    def test_orga_required_to_see(self):
        self.client.force_login(self.guest)
        response = self.client.get(
            reverse(
                "update_absorption",
                kwargs={"date": TODAY, "pk": self.absorption.pk},
            )
        )
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_date_shown_and_form_is_prefilled(self):
        response = self.client.get(
            reverse(
                "update_absorption",
                kwargs={"date": TODAY, "pk": self.absorption.pk},
            )
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/absorption_update.html")
        self.assertContains(response, TODAY.strftime("%A, %d. %B").replace(" 0", " "))
        self.assertContains(
            response,
            f'value="{self.signup.pk}" class="form-check-input" id="id_signup_1" required checked',
        )
        self.assertContains(response, self.absorption.amount)
        self.assertContains(
            response,
            f'value="{self.absorption.method}" class="form-check-input" id="id_method_0" required checked',
        )
        self.assertNotContains(response, PaymentMethods.CASH.label)

    def test_amount_cannot_be_negative_and_is_prefilled(self):
        new_amount = -42
        new_method = PaymentMethods.TWINT
        response = self.client.post(
            reverse(
                "update_absorption",
                kwargs={"date": TODAY, "pk": self.absorption.pk},
            ),
            data={
                "signup": self.signup.pk,
                "amount": new_amount,
                "method": new_method,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/absorption_update.html")
        self.assertContains(response, new_amount)
        self.absorption.refresh_from_db()
        self.assertContains(
            response,
            f'value="{self.signup.pk}" class="form-check-input" id="id_signup_1" required checked',
        )
        self.assertNotEqual(new_amount, self.absorption.amount)
        self.assertContains(
            response,
            f'value="{new_method}" class="form-check-input" id="id_method_1" required checked',
        )

    def test_update_absorption(self):
        new_amount = 23
        new_method = PaymentMethods.TWINT
        response = self.client.post(
            reverse(
                "update_absorption",
                kwargs={"date": TODAY, "pk": self.absorption.pk},
            ),
            data={
                "signup": self.signup.pk,
                "amount": new_amount,
                "method": new_method,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(
            response,
            f"Abschöpfung von {self.signup.pilot} über Fr. {new_amount} gespeichert.",
        )
        self.assertEqual(1, len(Absorption.objects.all()))
        self.absorption.refresh_from_db()
        self.assertEqual(new_amount, self.absorption.amount)
        self.assertEqual(new_method, self.absorption.method)

    def test_delete_absorption(self):
        response = self.client.post(
            reverse(
                "update_absorption",
                kwargs={"date": TODAY, "pk": self.absorption.pk},
            ),
            data={"reason": "Petrol", "amount": 24, "delete": ""},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, f"Abschöpfung gelöscht.")
        self.assertEqual(0, len(Absorption.objects.all()))

    def test_report_not_found_404(self):
        response = self.client.get(
            reverse(
                "update_absorption",
                kwargs={"date": YESTERDAY, "pk": self.absorption.pk},
            )
        )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)


class DatabaseCallsTests(TestCase):
    def setUp(self):
        num_pilots = randint(5, 10)

        orga = get_user_model().objects.create(
            email="orga@example.com", first_name="Orga", role=get_user_model().Role.ORGA
        )
        self.client.force_login(orga)

        pilots = [orga] + [
            get_user_model().objects.create(
                email=f"pilot_{i}@example.com", first_name=f"Pilot {i}"
            )
            for i in range(num_pilots)
        ]
        training = Training.objects.create(date=TODAY, emergency_mail_sender=orga)
        for pilot in pilots:
            signup = Signup.objects.create(pilot=pilot, training=training)
        self.signup = signup
        training.select_signups()
        self.report = Report.objects.create(training=training, cash_at_start=420)

    def test_absorption_create_view(self):
        with self.assertNumQueries(7):
            response = self.client.get(
                reverse("create_absorption", kwargs={"date": TODAY})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/absorption_create.html")

        with self.assertNumQueries(9):
            response = self.client.post(
                reverse("create_absorption", kwargs={"date": TODAY}),
                data={
                    "signup": self.signup.pk,
                    "amount": 420,
                    "method": PaymentMethods.BANK_TRANSFER,
                },
                follow=False,
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertEqual(1, len(Absorption.objects.all()))

    def test_absorption_update_view(self):
        absorption = Absorption.objects.create(
            report=self.report,
            signup=self.signup,
            amount=15,
            method=PaymentMethods.CASH,
        )
        with self.assertNumQueries(7):
            response = self.client.get(
                reverse(
                    "update_absorption",
                    kwargs={"date": TODAY, "pk": absorption.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/absorption_update.html")

        new_amount = 420
        new_method = PaymentMethods.TWINT
        with self.assertNumQueries(7):
            response = self.client.post(
                reverse(
                    "update_absorption",
                    kwargs={"date": TODAY, "pk": absorption.pk},
                ),
                data={
                    "signup": self.signup.pk,
                    "amount": new_amount,
                    "method": new_method,
                },
                follow=False,
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        absorption.refresh_from_db()
        self.assertEqual(new_amount, absorption.amount)
        self.assertEqual(new_method, absorption.method)

        with self.assertNumQueries(4):
            response = self.client.post(
                reverse(
                    "update_absorption",
                    kwargs={"date": TODAY, "pk": absorption.pk},
                ),
                data={"reason": "Petrol", "amount": 24, "delete": ""},
                follow=False,
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertEqual(0, len(Absorption.objects.all()))

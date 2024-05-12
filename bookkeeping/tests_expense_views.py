from datetime import timedelta
from http import HTTPStatus
import locale
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files import File
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Expense, Report
from trainings.models import Training


locale.setlocale(locale.LC_TIME, "de_CH")

TODAY = timezone.now().date()
YESTERDAY = TODAY - timedelta(days=1)


class ExpenseCreateViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            email="orga@example.com", first_name="Orga", role=get_user_model().Role.ORGA
        )
        self.client.force_login(self.orga)

        training = Training.objects.create(date=TODAY)
        self.report = Report.objects.create(training=training, cash_at_start=1337)

    def test_orga_required_to_see(self):
        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        response = self.client.get(reverse("create_expense", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_date_shown_and_reasons_listed(self):
        response = self.client.get(reverse("create_expense", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/expense_create.html")
        self.assertContains(response, TODAY.strftime("%A, %d. %B").replace(" 0", " "))
        for reason in Expense.Reasons:
            self.assertContains(response, reason.label)

    def test_amount_cannot_be_negative_and_is_prefilled(self):
        other_reason = "Other reason"
        amount = -42
        mocked_image = mock.MagicMock(spec=File)
        response = self.client.post(
            reverse("create_expense", kwargs={"date": TODAY}),
            data={
                "reason": Expense.Reasons.OTHER,
                "other_reason": other_reason,
                "amount": amount,
                "receipt": mocked_image,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/expense_create.html")
        self.assertContains(response, other_reason)
        self.assertContains(response, amount)

    @mock.patch("bookkeeping.forms.ExpenseCreateForm.send_mail")
    def test_failure_on_sending_mail(self, mocked_send_mail):
        mocked_send_mail.side_effect = lambda: 1 / 0
        reason = Expense.Reasons.GAS
        amount = 42
        mocked_image = mock.MagicMock(spec=File)
        with self.assertRaises(ZeroDivisionError):
            self.client.post(
                reverse("create_expense", kwargs={"date": TODAY}),
                data={"reason": reason, "amount": amount, "receipt": mocked_image},
                follow=True,
            )

        self.assertEqual(0, len(Expense.objects.all()))
        self.assertEqual(0, len(mail.outbox))

    def test_create_expense(self):
        reason = Expense.Reasons.GAS
        amount = 42
        mocked_image = mock.MagicMock(spec=File)
        response = self.client.post(
            reverse("create_expense", kwargs={"date": TODAY}),
            data={"reason": reason, "amount": amount, "receipt": mocked_image},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(
            response,
            f"Ausgabe für {Expense.Reasons.GAS.label} über Fr. {amount} gespeichert.",
        )

        self.assertEqual(1, len(Expense.objects.all()))
        created_expense = Expense.objects.first()
        self.assertEqual(Expense.Reasons.GAS.label, created_expense.reason)
        self.assertEqual(amount, created_expense.amount)

        # For more on testing mails see https://blog.ovalerio.net/archives/1856
        self.assertEqual(1, len(mail.outbox))
        self.assertEqual(mail.outbox[0].from_email, "dev@example.com")
        self.assertEqual(mail.outbox[0].to, ["finance@example.com"])
        self.assertTrue(str(amount) in mail.outbox[0].subject)
        self.assertTrue(reason.label in mail.outbox[0].subject)
        self.assertTrue(str(self.orga) in mail.outbox[0].body)
        self.assertTrue(TODAY.strftime("%x") in mail.outbox[0].body)
        self.assertEqual(1, len(mail.outbox[0].attachments))
        file_name, _, _ = mail.outbox[0].attachments[0]
        self.assertEqual(file_name, "receipt")

    def test_create_expense_for_other_reason(self):
        other_reason = "Other reason"
        amount = 42
        mocked_image = mock.MagicMock(spec=File)
        response = self.client.post(
            reverse("create_expense", kwargs={"date": TODAY}),
            data={
                "reason": Expense.Reasons.OTHER,
                "other_reason": other_reason,
                "amount": amount,
                "receipt": mocked_image,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(
            response, f"Ausgabe für {other_reason} über Fr. {amount} gespeichert."
        )

        self.assertEqual(1, len(Expense.objects.all()))
        created_expense = Expense.objects.first()
        self.assertEqual(other_reason, created_expense.reason)
        self.assertEqual(amount, created_expense.amount)

        self.assertEqual(1, len(mail.outbox))
        self.assertEqual(mail.outbox[0].from_email, "dev@example.com")
        self.assertEqual(mail.outbox[0].to, ["finance@example.com"])
        self.assertTrue(str(amount) in mail.outbox[0].subject)
        self.assertTrue(other_reason in mail.outbox[0].subject)
        self.assertTrue(str(self.orga) in mail.outbox[0].body)
        self.assertTrue(TODAY.strftime("%x") in mail.outbox[0].body)
        self.assertEqual(1, len(mail.outbox[0].attachments))
        file_name, _, _ = mail.outbox[0].attachments[0]
        self.assertEqual(file_name, "receipt")

    def test_report_not_found_404(self):
        response = self.client.get(
            reverse("create_expense", kwargs={"date": YESTERDAY})
        )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")


class ExpenseUpdateViewTests(TestCase):
    def setUp(self):
        orga = get_user_model().objects.create(
            email="orga@example.com", role=get_user_model().Role.ORGA
        )
        self.client.force_login(orga)

        training = Training.objects.create(date=TODAY)
        self.report = Report.objects.create(training=training, cash_at_start=1337)
        self.expense = Expense.objects.create(
            report=self.report, reason="Gas", amount=42
        )

    def test_orga_required_to_see(self):
        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        response = self.client.get(
            reverse("update_expense", kwargs={"date": TODAY, "pk": self.expense.pk})
        )
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_date_shown_and_form_is_prefilled(self):
        response = self.client.get(
            reverse("update_expense", kwargs={"date": TODAY, "pk": self.expense.pk})
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/expense_update.html")
        self.assertContains(response, TODAY.strftime("%A, %d. %B").replace(" 0", " "))
        self.assertContains(response, self.expense.reason)
        self.assertContains(response, self.expense.amount)

    def test_amount_cannot_be_negative_and_is_prefilled(self):
        new_reason = "Petrol"
        new_amount = -42
        response = self.client.post(
            reverse("update_expense", kwargs={"date": TODAY, "pk": self.expense.pk}),
            data={"reason": new_reason, "amount": new_amount},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/expense_update.html")
        self.assertContains(response, new_reason)
        self.assertContains(response, new_amount)
        self.expense.refresh_from_db()
        self.assertNotEqual(new_reason, self.expense.reason)
        self.assertNotEqual(new_amount, self.expense.amount)

    def test_update_expense(self):
        new_reason = "Petrol"
        new_amount = 23
        response = self.client.post(
            reverse("update_expense", kwargs={"date": TODAY, "pk": self.expense.pk}),
            data={"reason": new_reason, "amount": new_amount},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(
            response, f"Ausgabe für {new_reason} über Fr. {new_amount} gespeichert."
        )
        self.assertEqual(1, len(Expense.objects.all()))
        self.expense.refresh_from_db()
        self.assertEqual(new_reason, self.expense.reason)
        self.assertEqual(new_amount, self.expense.amount)

    def test_delete_expense(self):
        response = self.client.post(
            reverse("update_expense", kwargs={"date": TODAY, "pk": self.expense.pk}),
            data={"reason": "Petrol", "amount": 24, "delete": ""},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, f"Ausgabe gelöscht.")
        self.assertEqual(0, len(Expense.objects.all()))

    def test_wrong_date_does_not_404(self):
        response = self.client.get(
            reverse("update_expense", kwargs={"date": YESTERDAY, "pk": self.expense.pk})
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/expense_update.html")


class DatabaseCallsTests(TestCase):
    def setUp(self):
        orga = get_user_model().objects.create(
            email="orga@example.com", first_name="Orga", role=get_user_model().Role.ORGA
        )
        self.client.force_login(orga)

        training = Training.objects.create(date=TODAY, emergency_mail_sender=orga)
        training.select_signups()
        self.report = Report.objects.create(training=training, cash_at_start=420)

    def test_expense_create_view(self):
        with self.assertNumQueries(5):
            response = self.client.get(
                reverse("create_expense", kwargs={"date": TODAY})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/expense_create.html")

        mocked_image = mock.MagicMock(spec=File)
        with self.assertNumQueries(6):
            response = self.client.post(
                reverse("create_expense", kwargs={"date": TODAY}),
                data={
                    "reason": Expense.Reasons.GAS,
                    "amount": 42,
                    "receipt": mocked_image,
                },
                follow=False,
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertEqual(1, len(Expense.objects.all()))

    def test_expense_update_view(self):
        expense = Expense.objects.create(report=self.report, reason="Gas", amount=11)
        with self.assertNumQueries(4):
            response = self.client.get(
                reverse(
                    "update_expense",
                    kwargs={"date": TODAY, "pk": expense.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/expense_update.html")

        new_reason = "Petrol"
        new_amount = 23
        with self.assertNumQueries(4):
            response = self.client.post(
                reverse("update_expense", kwargs={"date": TODAY, "pk": expense.pk}),
                data={"reason": new_reason, "amount": new_amount},
                follow=False,
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        expense.refresh_from_db()
        self.assertEqual(new_reason, expense.reason)
        self.assertEqual(new_amount, expense.amount)

        with self.assertNumQueries(4):
            response = self.client.post(
                reverse("update_expense", kwargs={"date": TODAY, "pk": expense.pk}),
                data={"reason": "Petrol", "amount": 24, "delete": ""},
                follow=False,
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertEqual(0, len(Expense.objects.all()))

from datetime import date, timedelta
from http import HTTPStatus
import locale

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Expense, Report
from trainings.models import Training

locale.setlocale(locale.LC_TIME, "de_CH")

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


class ExpenseCreateViewTests(TestCase):
    def setUp(self):
        orga = get_user_model().objects.create(
            email="orga@example.com", role=get_user_model().Role.Orga
        )
        self.client.force_login(orga)

        training = Training.objects.create(date=TODAY)
        self.report = Report.objects.create(training=training, cash_at_start=1337)

    def test_orga_required_to_see(self):
        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        with self.assertNumQueries(2):
            response = self.client.get(
                reverse("create_expense", kwargs={"date": TODAY})
            )
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_date_shown(self):
        with self.assertNumQueries(5):
            response = self.client.get(
                reverse("create_expense", kwargs={"date": TODAY})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_expense.html")
        self.assertContains(response, TODAY.strftime("%A, %d. %B"))

    def test_amount_cannot_be_negative_and_is_prefilled(self):
        reason = "Gas"
        amount = -42
        with self.assertNumQueries(5):
            response = self.client.post(
                reverse("create_expense", kwargs={"date": TODAY}),
                data={"reason": reason, "amount": amount},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_expense.html")
        self.assertContains(response, reason)
        self.assertContains(response, amount)

    def test_create_expense(self):
        reason = "Gas"
        amount = 42
        with self.assertNumQueries(16):
            response = self.client.post(
                reverse("create_expense", kwargs={"date": TODAY}),
                data={"reason": reason, "amount": amount},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(
            response, f"Ausgabe für {reason} über {amount} gespeichert."
        )
        self.assertEqual(1, len(Expense.objects.all()))
        created_expense = Expense.objects.first()
        self.assertEqual(reason, created_expense.reason)
        self.assertEqual(amount, created_expense.amount)

    def test_no_existing_report_404(self):
        with self.assertNumQueries(4):
            response = self.client.get(
                reverse("create_expense", kwargs={"date": YESTERDAY})
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

from datetime import date, timedelta
from http import HTTPStatus
import locale

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Bill, Report, Run
from trainings.models import Signup, Training

locale.setlocale(locale.LC_TIME, "de_CH")

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


class BillCreateViewTests(TestCase):
    def setUp(self):
        orga = get_user_model().objects.create(
            first_name="Orga", email="orga@example.com", role=get_user_model().Role.Orga
        )
        self.client.force_login(orga)
        self.guest = get_user_model().objects.create(
            first_name="Guest", email="guest@example.com"
        )

        training = Training.objects.create(date=TODAY)
        now = timezone.now()
        self.orga_signup = Signup.objects.create(
            pilot=orga, training=training, signed_up_on=now
        )
        now += timedelta(hours=1)
        self.guest_signup = Signup.objects.create(
            pilot=self.guest, training=training, signed_up_on=now
        )

        self.report = Report.objects.create(training=training, cash_at_start=1337)
        now += timedelta(hours=1)
        Run(
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.Flight,
            created_on=now,
        ).save()
        now += timedelta(hours=1)
        Run(
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.Flight,
            created_on=now,
        ).save()
        now += timedelta(hours=1)
        Run(
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.Bus,
            created_on=now,
        ).save()

    def test_orga_required_to_see(self):
        self.client.force_login(self.guest)
        with self.assertNumQueries(2):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_pilot_and_date_shown(self):
        with self.assertNumQueries(8):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_bill.html")
        self.assertContains(response, self.guest)
        self.assertContains(response, TODAY.strftime("%a, %d. %b.").replace(" 0", " "))

    def test_form_is_prefilled(self):
        with self.assertNumQueries(8):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_bill.html")
        bill = Bill(signup=self.guest_signup, report=self.report)
        self.assertContains(response, bill.to_pay)

    def test_must_pay_enough(self):
        to_pay = Bill(signup=self.guest_signup, report=self.report).to_pay
        with self.assertNumQueries(12):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                ),
                data={"payed": to_pay - 1},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_bill.html")
        self.assertContains(response, f"{self.guest} muss {to_pay} bezahlen.")
        self.assertEqual(0, len(Bill.objects.all()))

    def test_create_bill(self):
        to_pay = Bill(signup=self.guest_signup, report=self.report).to_pay
        with self.assertNumQueries(29):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                ),
                data={"payed": to_pay},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(response, f"Bezahlung von {self.guest} gespeichert.")
        self.assertEqual(1, len(Bill.objects.all()))
        created_bill = Bill.objects.first()
        self.assertEqual(to_pay, created_bill.payed)

    def test_cannot_pay_twice(self):
        with self.assertNumQueries(29):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                ),
                data={"payed": 420},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertEqual(1, len(Bill.objects.all()))

        with self.assertNumQueries(25):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                ),
                data={"payed": 420},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(response, f"{self.guest} hat bereits bezahlt.")
        self.assertEqual(1, len(Bill.objects.all()))

    def test_signup_not_found_404(self):
        with self.assertNumQueries(4):
            response = self.client.get(
                reverse("create_bill", kwargs={"date": TODAY, "signup": 666})
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

    def test_report_not_fround_404(self):
        training = Training.objects.create(date=TOMORROW)
        now = timezone.now()
        signup = Signup.objects.create(
            pilot=self.guest, training=training, signed_up_on=now
        )
        with self.assertNumQueries(6):
            response = self.client.get(
                reverse("create_bill", kwargs={"date": TODAY, "signup": signup.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

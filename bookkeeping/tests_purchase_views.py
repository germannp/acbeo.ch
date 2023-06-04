from datetime import timedelta
from http import HTTPStatus
import locale

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Bill, PaymentMethods, Purchase, Report, Run
from trainings.models import Signup, Training


locale.setlocale(locale.LC_TIME, "de_CH")

TODAY = timezone.now().date()
YESTERDAY = TODAY - timedelta(days=1)


class PurchaseCreateViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            email="orga@example.com", role=get_user_model().Role.ORGA
        )
        self.client.force_login(self.orga)

        training = Training.objects.create(date=TODAY)
        now = timezone.now()
        self.signup = Signup.objects.create(
            pilot=self.orga, training=training, signed_up_on=now
        )

        self.report = Report.objects.create(training=training, cash_at_start=1337)

    def test_orga_required_to_see(self):
        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        with self.assertNumQueries(3):
            response = self.client.get(
                reverse(
                    "create_purchase", kwargs={"date": TODAY, "signup": self.signup.pk}
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_pilot_and_date_shown_and_items_listed(self):
        with self.assertNumQueries(9):
            response = self.client.get(
                reverse(
                    "create_purchase", kwargs={"date": TODAY, "signup": self.signup.pk}
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/purchase_create.html")
        self.assertContains(response, self.orga)
        self.assertContains(
            response,
            TODAY.strftime("%a., %d. %b.").replace(" 0", " ").replace("..", "."),
        )
        for item in Purchase.Items:
            self.assertContains(response, item.label)

    def test_create_purchase(self):
        with self.assertNumQueries(22):
            response = self.client.post(
                reverse(
                    "create_purchase", kwargs={"date": TODAY, "signup": self.signup.pk}
                ),
                data={"item": Purchase.Items.REARMING_KIT},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        self.assertEqual(1, len(Purchase.objects.all()))
        created_purchase = Purchase.objects.first()
        self.assertTrue(
            created_purchase.description in Purchase.Items.REARMING_KIT.label
        )
        self.assertTrue(
            str(created_purchase.price) in Purchase.Items.REARMING_KIT.label
        )

    def test_cannot_create_purchase_for_paid_signup(self):
        Bill(
            signup=self.signup,
            report=self.report,
            prepaid_flights=0,
            amount=42,
            method=PaymentMethods.CASH,
        ).save()
        with self.assertNumQueries(25):
            response = self.client.post(
                reverse(
                    "create_purchase", kwargs={"date": TODAY, "signup": self.signup.pk}
                ),
                data={"item": Purchase.Items.REARMING_KIT},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, f"{self.orga} hat bereits bezahlt.")

    def test_signup_not_found_404(self):
        with self.assertNumQueries(6):
            response = self.client.get(
                reverse("create_purchase", kwargs={"date": TODAY, "signup": 666})
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

    def test_report_not_found_404(self):
        Report.objects.all().delete()
        with self.assertNumQueries(8):
            response = self.client.get(
                reverse(
                    "create_purchase", kwargs={"date": TODAY, "signup": self.signup.pk}
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")


class PurchaseDeleteViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            email="orga@example.com", role=get_user_model().Role.ORGA
        )
        self.client.force_login(self.orga)

        self.training = Training.objects.create(date=TODAY)
        now = timezone.now()
        self.signup = Signup.objects.create(
            pilot=self.orga, training=self.training, signed_up_on=now
        )
        self.report = Report.objects.create(training=self.training, cash_at_start=1337)
        self.purchase = Purchase.objects.create(
            signup=self.signup, report=self.report, description="Description", price=42
        )

    def test_orga_required_to_see(self):
        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        with self.assertNumQueries(3):
            response = self.client.get(
                reverse(
                    "delete_purchase", kwargs={"date": TODAY, "pk": self.purchase.pk}
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_pilot_and_desciption_shown(self):
        with self.assertNumQueries(8):
            response = self.client.get(
                reverse(
                    "delete_purchase", kwargs={"date": TODAY, "pk": self.purchase.pk}
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/purchase_confirm_delete.html")
        self.assertContains(response, self.orga)
        self.assertContains(response, self.purchase.description)
        self.assertContains(
            response,
            reverse("create_bill", kwargs={"date": TODAY, "signup": self.signup.pk}),
        )

    def test_delete_purchase(self):
        with self.assertNumQueries(22):
            response = self.client.post(
                reverse(
                    "delete_purchase", kwargs={"date": TODAY, "pk": self.purchase.pk}
                ),
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        self.assertEqual(0, len(Purchase.objects.all()))

    def test_delete_day_pass(self):
        guest = get_user_model().objects.create(email="guest@example.com")
        now = timezone.now()
        signup = Signup.objects.create(
            pilot=guest, training=self.training, signed_up_on=now
        )
        for i in range(3):
            Run(
                signup=signup,
                report=self.report,
                kind=Run.Kind.FLIGHT,
                created_on=now + timedelta(hours=i),
            ).save()
        self.assertTrue(signup.needs_day_pass)
        Purchase.save_day_pass(signup, self.report)
        day_pass = Purchase.objects.last()
        self.assertEqual(Purchase.DAY_PASS_DESCRIPTION, day_pass.description)
        with self.assertNumQueries(23):
            response = self.client.post(
                reverse("delete_purchase", kwargs={"date": TODAY, "pk": day_pass.pk}),
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        self.assertEqual(1, len(Purchase.objects.all()))

    def test_cannot_delete_purchase_for_paid_signup(self):
        Bill(
            signup=self.signup,
            report=self.report,
            prepaid_flights=0,
            amount=42,
            method=PaymentMethods.CASH,
        ).save()
        with self.assertNumQueries(27):
            response = self.client.post(
                reverse(
                    "delete_purchase", kwargs={"date": TODAY, "pk": self.purchase.pk}
                ),
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, f"{self.orga} hat bereits bezahlt.")

    def test_purchase_not_found_404(self):
        with self.assertNumQueries(6):
            response = self.client.get(
                reverse("delete_purchase", kwargs={"date": TODAY, "pk": 666})
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

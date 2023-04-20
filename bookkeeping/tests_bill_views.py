from datetime import date, timedelta
from http import HTTPStatus
import locale

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Bill, PaymentMethods, Purchase, Report, Run
from trainings.models import Signup, Training

locale.setlocale(locale.LC_TIME, "de_CH")

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


class BillListViewTests(TestCase):
    def setUp(self):
        self.guest = get_user_model().objects.create(
            email="guest@example.com", prepaid_flights=1337
        )
        self.client.force_login(self.guest)

        training = Training.objects.create(date=TODAY)
        signup = Signup.objects.create(pilot=self.guest, training=training)
        report = Report.objects.create(training=training, cash_at_start=666)
        self.purchase = Purchase.save_day_pass(signup, report)
        self.bill = Bill.objects.create(
            signup=signup,
            report=report,
            prepaid_flights=1312,
            amount=420,
            method=PaymentMethods.CASH,
        )

        self.guest_2 = get_user_model().objects.create(email="guest_2@example.com")
        other_signup = Signup.objects.create(pilot=self.guest_2, training=training)
        self.other_bill = Bill.objects.create(
            signup=other_signup,
            report=report,
            prepaid_flights=0,
            amount=666,
            method=PaymentMethods.CASH,
        )

    def test_login_required(self):
        with self.assertNumQueries(3):
            response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, reverse("bills"))

        self.client.logout()
        with self.assertNumQueries(1):
            response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertNotContains(response, reverse("bills"))

        with self.assertNumQueries(0):
            response = self.client.get(reverse("bills"), follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/login.html")

    def test_pagination_by_year(self):
        with self.assertNumQueries(7):
            response = self.client.get(reverse("bills"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_list.html")
        self.assertNotContains(
            response, reverse("bills", kwargs={"year": TODAY.year + 1})
        )
        self.assertNotContains(
            response, reverse("bills", kwargs={"year": TODAY.year - 1})
        )

        for date, pilot in [
            (YESTERDAY, self.guest),
            (TODAY - timedelta(days=365), self.guest),
            (TODAY - 2 * timedelta(days=365), self.guest_2),
            (TODAY - 3 * timedelta(days=365), self.guest),
        ]:
            training = Training.objects.create(date=date)
            signup = Signup.objects.create(pilot=pilot, training=training)
            report = Report.objects.create(training=training, cash_at_start=1337)
            Bill(
                signup=signup,
                report=report,
                prepaid_flights=0,
                amount=420,
                method=PaymentMethods.CASH,
            ).save()

        with self.assertNumQueries(7):
            response = self.client.get(reverse("bills"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_list.html")
        self.assertContains(response, reverse("bills", kwargs={"year": TODAY.year - 1}))
        self.assertNotContains(
            response, reverse("bills", kwargs={"year": TODAY.year - 2})
        )
        self.assertNotContains(
            response, reverse("bills", kwargs={"year": TODAY.year - 3})
        )

        with self.assertNumQueries(6):
            response = self.client.get(
                reverse("bills", kwargs={"year": TODAY.year - 1})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_list.html")
        self.assertContains(response, reverse("bills", kwargs={"year": TODAY.year}))
        self.assertNotContains(
            response, reverse("bills", kwargs={"year": TODAY.year - 2})
        )
        self.assertContains(response, reverse("bills", kwargs={"year": TODAY.year - 3}))

        with self.assertNumQueries(6):
            response = self.client.get(
                reverse("bills", kwargs={"year": TODAY.year - 3})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_list.html")
        self.assertNotContains(response, reverse("bills", kwargs={"year": TODAY.year}))
        self.assertContains(response, reverse("bills", kwargs={"year": TODAY.year - 1}))
        self.assertNotContains(
            response, reverse("bills", kwargs={"year": TODAY.year - 4})
        )

    def test_only_logged_in_pilots_bills_shown(self):
        with self.assertNumQueries(7):
            response = self.client.get(reverse("bills"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_list.html")
        self.assertContains(response, self.bill.amount)
        self.assertNotContains(response, self.other_bill.amount)

    def test_purchase_shown(self):
        with self.assertNumQueries(7):
            response = self.client.get(reverse("bills"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_list.html")
        self.assertContains(response, self.purchase.description)

    def test_prepaid_flights_shown(self):
        with self.assertNumQueries(7):
            response = self.client.get(reverse("bills"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_list.html")
        self.assertContains(response, self.guest.prepaid_flights)

    def test_no_bills_in_year_404(self):
        with self.assertNumQueries(3):
            response = self.client.get(reverse("bills", kwargs={"year": 1984}))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        self.bill.delete()
        with self.assertNumQueries(3):
            response = self.client.get(reverse("bills"))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")


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
        with self.assertNumQueries(9):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        self.assertContains(response, self.guest)
        self.assertContains(response, TODAY.strftime("%a, %d. %b.").replace(" 0", " "))

    def test_prepaid_flights_shown(self):
        with self.assertNumQueries(9):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        bill = Bill(signup=self.guest_signup, report=self.report)
        self.assertContains(response, f'value="{bill.num_prepaid_flights}"')
        self.assertContains(response, f'value="{bill.to_pay}"')
        self.assertNotContains(response, "Mit Abo bezahlt")
        self.assertNotContains(response, "Flüge gutgeschrieben")

        self.guest.prepaid_flights = 10
        self.guest.save()
        with self.assertNumQueries(9):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        bill = Bill(signup=self.guest_signup, report=self.report)
        self.assertContains(response, f'value="{bill.num_prepaid_flights}"')
        self.assertContains(response, f'value="{bill.to_pay}"')
        self.assertContains(response, "Mit Abo bezahlt")

        for run in Run.objects.all():
            if not run.is_service:
                run.delete()
        with self.assertNumQueries(9):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        bill = Bill(signup=self.guest_signup, report=self.report)
        self.assertContains(response, f'value="{bill.num_prepaid_flights}"')
        self.assertContains(response, f'value="{bill.to_pay}"')
        self.assertContains(response, "Flüge gutgeschrieben")

    def test_purchase_shown(self):
        purchase = Purchase.objects.create(
            signup=self.guest_signup,
            report=self.report,
            description="Description",
            price=42,
        )
        with self.assertNumQueries(9):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        self.assertContains(response, purchase.description)
        self.assertContains(response, purchase.price)
        self.assertContains(
            response,
            reverse("delete_purchase", kwargs={"date": TODAY, "pk": purchase.pk}),
        )
        self.assertContains(
            response,
            reverse(
                "create_purchase",
                kwargs={"date": TODAY, "signup": self.guest_signup.pk},
            ),
        )

    def test_creates_day_pass(self):
        Run(
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.Flight,
            created_on=timezone.now() + timedelta(hours=7),
        ).save()
        self.assertTrue(self.guest_signup.needs_day_pass)
        with self.assertNumQueries(12):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        self.assertContains(response, Purchase.DAY_PASS_DESCRIPTION)
        self.assertEqual(1, len(Purchase.objects.all()))

    def test_form_is_prefilled(self):
        with self.assertNumQueries(9):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        bill = Bill(signup=self.guest_signup, report=self.report)
        self.assertContains(response, f'value="{bill.num_prepaid_flights}"')
        self.assertContains(response, f'value="{bill.to_pay}"')
        self.assertNotContains(response, "Mit Abo bezahlt")
        self.assertContains(
            response,
            f'value="{PaymentMethods.CASH}" class="form-check-input" id="id_method_0" required checked',
        )
        self.assertNotContains(response, PaymentMethods.BANK_TRANSFER.label)

    def test_must_pay_enough(self):
        to_pay = Bill(signup=self.guest_signup, report=self.report).to_pay
        with self.assertNumQueries(14):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                ),
                data={
                    "prepaid_flights": 0,
                    "amount": to_pay - 1,
                    "method": PaymentMethods.CASH,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        self.assertContains(response, f"{self.guest} muss Fr. {to_pay} bezahlen.")
        self.assertEqual(0, len(Bill.objects.all()))

    def test_create_bill(self):
        to_pay = Bill(signup=self.guest_signup, report=self.report).to_pay
        method = PaymentMethods.TWINT
        with self.assertNumQueries(31):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                ),
                data={
                    "prepaid_flights": 0,
                    "amount": to_pay,
                    "method": method,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, f"Bezahlung von {self.guest} gespeichert.")
        self.assertEqual(1, len(Bill.objects.all()))
        created_bill = Bill.objects.first()
        self.assertEqual(to_pay, created_bill.amount)
        self.assertEqual(method, created_bill.method)

    def test_cannot_pay_twice(self):
        Bill(
            signup=self.guest_signup,
            report=self.report,
            prepaid_flights=0,
            amount=42,
            method=PaymentMethods.CASH,
        ).save()
        with self.assertNumQueries(29):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                ),
                data={
                    "prepaid_flights": 0,
                    "amount": 420,
                    "method": PaymentMethods.CASH,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
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


class BillUpdateViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            first_name="Orga", email="orga@example.com", role=get_user_model().Role.Orga
        )
        self.client.force_login(self.orga)

        training = Training.objects.create(date=TODAY)
        now = timezone.now()
        self.signup = Signup.objects.create(
            pilot=self.orga, training=training, signed_up_on=now
        )
        self.report = Report.objects.create(training=training, cash_at_start=1337)
        now += timedelta(hours=1)
        Run(
            signup=self.signup, report=self.report, kind=Run.Kind.Flight, created_on=now
        ).save()
        now += timedelta(hours=1)
        Run(
            signup=self.signup, report=self.report, kind=Run.Kind.Flight, created_on=now
        ).save()
        now += timedelta(hours=1)
        Run(
            signup=self.signup, report=self.report, kind=Run.Kind.Boat, created_on=now
        ).save()
        self.purchase = Purchase.objects.create(
            signup=self.signup, report=self.report, description="Description", price=42
        )
        self.bill = Bill.objects.create(
            signup=self.signup,
            report=self.report,
            prepaid_flights=0,
            amount=42,
            method=PaymentMethods.CASH,
        )

    def test_orga_required_to_see(self):
        guest = get_user_model().objects.create(
            first_name="Guest", email="guest@example.com"
        )
        self.client.force_login(guest)
        with self.assertNumQueries(2):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_pilot_and_date_shown(self):
        with self.assertNumQueries(9):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_update.html")
        self.assertContains(response, self.orga)
        self.assertContains(response, TODAY.strftime("%a, %d. %b.").replace(" 0", " "))

    def test_prepaid_flights_shown(self):
        with self.assertNumQueries(9):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_update.html")
        self.assertContains(response, f'value="{self.bill.num_prepaid_flights}"')
        self.assertNotContains(response, "Mit Abo bezahlt")
        self.assertNotContains(response, "Flüge gutgeschrieben")

        self.orga.prepaid_flights = 10
        self.orga.save()
        with self.assertNumQueries(9):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_update.html")
        self.assertContains(response, f'value="{self.bill.num_prepaid_flights}"')
        self.assertContains(response, f'value="{self.bill.to_pay}"')
        self.assertContains(response, "Mit Abo bezahlt")

        for run in Run.objects.all():
            if not run.is_service:
                run.delete()
        with self.assertNumQueries(9):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_update.html")
        self.assertContains(response, f'value="{self.bill.num_prepaid_flights}"')
        self.assertContains(response, f'value="{self.bill.to_pay}"')
        self.assertContains(response, "Flüge gutgeschrieben")

    def test_purchase_shown(self):
        with self.assertNumQueries(9):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_update.html")
        self.assertContains(response, self.purchase.description)
        self.assertContains(response, self.purchase.price)
        self.assertNotContains(
            response,
            reverse("delete_purchase", kwargs={"date": TODAY, "pk": self.purchase.pk}),
        )
        self.assertNotContains(
            response,
            reverse(
                "create_purchase", kwargs={"date": TODAY, "signup": self.signup.pk}
            ),
        )

    def test_form_is_prefilled(self):
        with self.assertNumQueries(9):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_update.html")
        self.assertContains(response, f'value="{self.bill.num_prepaid_flights}"')
        self.assertContains(response, f'value="{self.bill.amount}"')
        self.assertNotContains(response, "Mit Abo bezahlt")
        self.assertContains(
            response,
            f'value="{self.bill.method}" class="form-check-input" id="id_method_0" required checked',
        )
        self.assertNotContains(response, PaymentMethods.BANK_TRANSFER.label)

    def test_must_pay_enough(self):
        to_pay = Bill(signup=self.signup, report=self.report).to_pay
        with self.assertNumQueries(9):
            response = self.client.post(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk}),
                data={
                    "prepaid_flights": 0,
                    "amount": to_pay - 1,
                    "method": PaymentMethods.CASH,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_update.html")
        self.assertContains(response, f"{self.orga} muss Fr. {to_pay} bezahlen.")
        self.assertEqual(1, len(Bill.objects.all()))

    def test_update_bill(self):
        to_pay = Bill(signup=self.signup, report=self.report).to_pay
        method = PaymentMethods.TWINT
        with self.assertNumQueries(26):
            response = self.client.post(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk}),
                data={
                    "prepaid_flights": 0,
                    "amount": to_pay,
                    "method": method,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, f"Bezahlung von {self.orga} gespeichert.")
        self.assertEqual(1, len(Bill.objects.all()))
        created_bill = Bill.objects.first()
        self.assertEqual(to_pay, created_bill.amount)
        self.assertEqual(method, created_bill.method)

    def test_delete_bill(self):
        with self.assertNumQueries(25):
            response = self.client.post(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk}),
                data={"delete": ""},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, f"Abrechnung gelöscht.")
        self.assertEqual(3, len(Run.objects.all()))
        self.assertEqual(1, len(Purchase.objects.all()))

    def test_bill_not_found_404(self):
        with self.assertNumQueries(4):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": 666})
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

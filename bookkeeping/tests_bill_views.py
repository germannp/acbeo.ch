from datetime import timedelta
from http import HTTPStatus
from random import randint
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
        with self.assertNumQueries(5):
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
        with self.assertNumQueries(10):
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

        with self.assertNumQueries(10):
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

        with self.assertNumQueries(9):
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

        with self.assertNumQueries(9):
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
        with self.assertNumQueries(10):
            response = self.client.get(reverse("bills"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_list.html")
        self.assertContains(response, self.bill.amount)
        self.assertNotContains(response, self.other_bill.amount)

    def test_purchase_shown(self):
        with self.assertNumQueries(10):
            response = self.client.get(reverse("bills"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_list.html")
        self.assertContains(response, self.purchase.description)

    def test_prepaid_flights_shown(self):
        with self.assertNumQueries(10):
            response = self.client.get(reverse("bills"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_list.html")
        self.assertContains(response, self.guest.prepaid_flights)

    def test_no_bills_404(self):
        with self.assertNumQueries(5):
            response = self.client.get(reverse("bills", kwargs={"year": 1984}))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        self.bill.delete()
        with self.assertNumQueries(5):
            response = self.client.get(reverse("bills"))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        with self.assertNumQueries(5):
            response = self.client.get(reverse("home"))
        self.assertNotContains(response, reverse("bills"))


class PilotListViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            first_name="Orga", email="orga@example.com", role=get_user_model().Role.ORGA
        )
        self.client.force_login(self.orga)
        self.guest = get_user_model().objects.create(
            first_name="Guest", email="guest@example.com"
        )

        for i in range(3):
            training = Training.objects.create(date=TODAY - timedelta(days=i))
            report = Report.objects.create(training=training, cash_at_start=420)
            for pilot in [self.orga, self.guest]:
                if pilot == self.guest and i == 2:
                    continue

                signup = Signup.objects.create(pilot=pilot, training=training)
                for j in range(2):
                    Run(
                        signup=signup,
                        report=report,
                        kind=Run.Kind.BOAT,
                        created_on=timezone.now() - timedelta(minutes=j),
                    ).save()
                for j in range(4):
                    Run(
                        signup=signup,
                        report=report,
                        kind=Run.Kind.FLIGHT,
                        created_on=timezone.now() - timedelta(minutes=7 + j),
                    ).save()
                Bill(
                    signup=signup,
                    report=report,
                    prepaid_flights=3,
                    amount=15,
                    method=PaymentMethods.TWINT,
                ).save()
            training.select_signups()

    def test_orga_required_to_see(self):
        self.client.force_login(self.guest)
        with self.assertNumQueries(4):
            response = self.client.get(reverse("pilots"))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_orga_required_to_see_menu(self):
        with self.assertNumQueries(6):
            response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, reverse("pilots"))

        self.client.force_login(self.guest)
        with self.assertNumQueries(5):
            response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertNotContains(response, reverse("pilots") + '"')

    def test_pagination_by_year(self):
        with self.assertNumQueries(11):
            response = self.client.get(reverse("pilots"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/pilot_list.html")
        self.assertNotContains(
            response, reverse("pilots", kwargs={"year": TODAY.year + 1})
        )
        self.assertNotContains(
            response, reverse("pilots", kwargs={"year": TODAY.year - 1})
        )

        for date, pilot in [
            (TODAY - timedelta(days=365), self.guest),
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

        with self.assertNumQueries(11):
            response = self.client.get(reverse("pilots"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/pilot_list.html")
        self.assertContains(
            response, reverse("pilots", kwargs={"year": TODAY.year - 1})
        )
        self.assertNotContains(
            response, reverse("pilots", kwargs={"year": TODAY.year - 2})
        )
        self.assertNotContains(
            response, reverse("pilots", kwargs={"year": TODAY.year - 3})
        )

        with self.assertNumQueries(10):
            response = self.client.get(
                reverse("pilots", kwargs={"year": TODAY.year - 1})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/pilot_list.html")
        self.assertContains(response, reverse("pilots", kwargs={"year": TODAY.year}))
        self.assertNotContains(
            response, reverse("pilots", kwargs={"year": TODAY.year - 2})
        )
        self.assertContains(
            response, reverse("pilots", kwargs={"year": TODAY.year - 3})
        )

        with self.assertNumQueries(10):
            response = self.client.get(
                reverse("pilots", kwargs={"year": TODAY.year - 3})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/pilot_list.html")
        self.assertNotContains(response, reverse("pilots", kwargs={"year": TODAY.year}))
        self.assertContains(
            response, reverse("pilots", kwargs={"year": TODAY.year - 1})
        )
        self.assertNotContains(
            response, reverse("pilots", kwargs={"year": TODAY.year - 4})
        )

    def test_stats_shown(self):
        with self.assertNumQueries(11):
            response = self.client.get(reverse("pilots"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/pilot_list.html")

        guest_row = (
            response.content.decode(response.charset)
            .split("Guest")[1]
            .split("</tr>")[0]
            .replace(" ", "")
            .replace("\n", "")
        )
        orga_row = (
            response.content.decode(response.charset)
            .split("Orga")[1]
            .split("</tr>")[0]
            .replace(" ", "")
            .replace("\n", "")
        )
        self.assertTrue("<td>2</td>" in guest_row)  # Days
        self.assertTrue("<td>3</td>" in orga_row)
        self.assertTrue("<td>4</td>" in guest_row)  # Services
        self.assertTrue("<td>6</td>" in orga_row)
        self.assertTrue("<td>8</td>" in guest_row)  # Flights
        self.assertTrue("<td>12</td>" in orga_row)

    def test_sorting_by_flights(self):
        with self.assertNumQueries(11):
            response = self.client.get(reverse("pilots"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/pilot_list.html")

        response_before_guest = str(response.content).split("Guest")[0]
        self.assertTrue("Orga" in response_before_guest)

    def test_no_bills_404(self):
        with self.assertNumQueries(6):
            response = self.client.get(reverse("pilots", kwargs={"year": 1984}))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        Bill.objects.all().delete()
        with self.assertNumQueries(6):
            response = self.client.get(reverse("pilots"))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")


class BillCreateViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            first_name="Orga", email="orga@example.com", role=get_user_model().Role.ORGA
        )
        self.client.force_login(self.orga)
        self.guest = get_user_model().objects.create(
            first_name="Guest", email="guest@example.com"
        )

        self.training = Training.objects.create(date=TODAY)
        now = timezone.now()
        self.orga_signup = Signup.objects.create(
            pilot=self.orga, training=self.training, signed_up_on=now
        )
        now += timedelta(hours=1)
        self.guest_signup = Signup.objects.create(
            pilot=self.guest, training=self.training, signed_up_on=now
        )

        self.report = Report.objects.create(training=self.training, cash_at_start=1337)
        Bill(
            signup=self.orga_signup,
            report=self.report,
            prepaid_flights=0,
            amount=0,
            method=PaymentMethods.CASH,
        ).save()

        now += timedelta(hours=1)
        Run(
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.FLIGHT,
            created_on=now,
        ).save()
        now += timedelta(hours=1)
        Run(
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.FLIGHT,
            created_on=now,
        ).save()
        now += timedelta(hours=1)
        Run(
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.BUS,
            created_on=now,
        ).save()

    def test_orga_required_to_see(self):
        self.client.force_login(self.guest)
        with self.assertNumQueries(4):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_pilot_and_date_shown(self):
        with self.assertNumQueries(16):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        self.assertContains(response, self.guest)
        self.assertContains(
            response,
            TODAY.strftime("%a., %d. %b.").replace(" 0", " ").replace("..", "."),
        )

    def test_prepaid_flights_shown(self):
        with self.assertNumQueries(16):
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
        self.assertNotContains(response, "<td>Mit Abo bezahlt</td>")
        self.assertNotContains(response, "<td>Flüge gutgeschrieben</td>")

        self.guest.prepaid_flights = 10
        self.guest.save()
        with self.assertNumQueries(16):
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
        self.assertContains(response, "<td>Mit Abo bezahlt</td>")

        for run in Run.objects.all():
            if not run.is_service:
                run.delete()
        with self.assertNumQueries(16):
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
        self.assertContains(response, "<td>Flüge gutgeschrieben</td>")

    def test_purchase_shown(self):
        purchase = Purchase.objects.create(
            signup=self.guest_signup,
            report=self.report,
            description="Description",
            price=42,
        )
        with self.assertNumQueries(16):
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

    def test_warning_for_previous_unpaid_signup(self):
        yesterdays_training = Training.objects.create(date=YESTERDAY)
        now = timezone.now()
        yesterdays_signup = Signup.objects.create(
            pilot=self.guest, training=yesterdays_training, signed_up_on=now
        )
        yesterdays_report = Report.objects.create(
            training=yesterdays_training, cash_at_start=1337
        )
        Run(
            signup=yesterdays_signup,
            report=yesterdays_report,
            kind=Run.Kind.FLIGHT,
            created_on=now,
        ).save()
        self.assertTrue(yesterdays_signup.must_be_paid)

        with self.assertNumQueries(19):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        url = reverse(
            "create_bill",
            kwargs={"date": YESTERDAY, "signup": yesterdays_signup.pk},
        )
        date = YESTERDAY.strftime("%A, %d. %B").replace(" 0", " ")
        self.assertContains(
            response,
            f'{self.guest} wurde für <a href="{url}">{date}</a>, nicht abgerechnet.',
        )

    def test_creates_day_pass(self):
        Run(
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.FLIGHT,
            created_on=timezone.now() + timedelta(hours=7),
        ).save()
        self.assertTrue(self.guest_signup.needs_day_pass)
        with self.assertNumQueries(19):
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
        with self.assertNumQueries(16):
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
        self.assertNotContains(response, "<td>Mit Abo bezahlt</td>")
        self.assertContains(
            response,
            f'value="{PaymentMethods.CASH}" class="form-check-input" id="id_method_0" required checked',
        )
        self.assertNotContains(response, PaymentMethods.BANK_TRANSFER.label)

    def test_must_pay_enough(self):
        to_pay = Bill(signup=self.guest_signup, report=self.report).to_pay
        with self.assertNumQueries(18):
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
        self.guest_signup.refresh_from_db()

    def test_make_orga(self):
        with self.assertNumQueries(24):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                ),
                data={"make-orga": ""},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        self.assertContains(response, "Zu Tagesleiter·in gemacht.")
        self.guest_signup.refresh_from_db()
        self.assertTrue(self.guest_signup.is_training_orga)
        self.report.refresh_from_db()
        self.assertEqual(self.guest_signup, self.report.orga_1)

    def test_already_orga(self):
        self.report.orga_1 = self.guest_signup
        self.report.save()
        self.assertTrue(self.guest_signup.is_training_orga)
        with self.assertNumQueries(23):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                ),
                data={"make-orga": ""},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        self.assertContains(response, "Ist bereits Tagesleiter·in.")

    def test_cannot_make_paid_signup_orga(self):
        self.assertTrue(self.orga_signup.is_paid)
        with self.assertNumQueries(25):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.orga_signup.pk},
                ),
                data={"make-orga": ""},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(
            response,
            f"Nicht zu Tagesleiter·in gemacht, {self.orga} hat bereits bezahlt.",
        )
        self.assertFalse(self.guest_signup.is_training_orga)

    def test_no_more_than_two_orgas(self):
        self.report.orga_1 = self.orga_signup
        self.report.orga_2 = self.guest_signup
        self.report.save()
        pilot = get_user_model().objects.create(
            first_name="Pilot", email="pilot@example.com"
        )
        signup = Signup.objects.create(
            pilot=pilot, training=self.training, signed_up_on=timezone.now()
        )
        with self.assertNumQueries(30):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": signup.pk},
                ),
                data={"make-orga": ""},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        self.assertContains(
            response,
            f"Nicht zu Tagesleiter·in gemacht, {self.orga} und "
            f"{self.guest} sind bereits als Tagesleiter·innen gespeichert.",
        )
        signup.refresh_from_db()
        self.assertFalse(signup.is_training_orga)

    def test_undo_orga(self):
        self.report.orga_1 = self.guest_signup
        self.report.save()
        self.assertTrue(self.guest_signup.is_training_orga)
        with self.assertNumQueries(23):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                ),
                data={"undo-orga": ""},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        self.assertContains(response, "Tagesleiter·in entfernt.")
        self.guest_signup.refresh_from_db()
        self.assertFalse(self.guest_signup.is_training_orga)

    def test_undo_first_of_two_orgas(self):
        self.report.orga_1 = self.guest_signup
        self.report.orga_2 = self.orga_signup
        self.report.save()
        with self.assertNumQueries(25):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                ),
                data={"undo-orga": ""},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")
        self.assertContains(response, "Tagesleiter·in entfernt.")
        self.guest_signup.refresh_from_db()
        self.assertFalse(self.guest_signup.is_training_orga)
        self.report.refresh_from_db()
        self.assertEqual(self.orga_signup, self.report.orga_1)

    def test_cannot_undo_orga_for_paid_signup(self):
        self.report.orga_1 = self.orga_signup
        self.report.save()
        self.assertTrue(self.orga_signup.is_paid)
        self.assertTrue(self.orga_signup.is_training_orga)
        with self.assertNumQueries(27):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.orga_signup.pk},
                ),
                data={"undo-orga": ""},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(
            response, f"Tagesleiter·in nicht entfernt, {self.orga} hat bereits bezahlt."
        )

    def test_create_bill(self):
        to_pay = Bill(signup=self.guest_signup, report=self.report).to_pay
        method = PaymentMethods.CASH
        with self.assertNumQueries(30):
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
        self.guest_signup.refresh_from_db()
        self.assertTrue(self.guest_signup.is_paid)
        self.assertEqual(to_pay, self.guest_signup.bill.amount)
        self.assertEqual(method, self.guest_signup.bill.method)

    def test_create_bill_redirect_to_twint(self):
        to_pay = Bill(signup=self.guest_signup, report=self.report).to_pay
        method = PaymentMethods.TWINT
        with self.assertNumQueries(14):
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
        self.assertTemplateUsed(response, "bookkeeping/twint.html")
        self.assertContains(response, f"Bezahlung von {self.guest} gespeichert.")
        self.assertContains(response, f"Betrag Fr. {to_pay}")
        self.assertContains(response, reverse("update_report", kwargs={"date": TODAY}))
        self.guest_signup.refresh_from_db()
        self.assertTrue(self.guest_signup.is_paid)
        self.assertEqual(to_pay, self.guest_signup.bill.amount)
        self.assertEqual(method, self.guest_signup.bill.method)

    def test_cannot_pay_twice(self):
        Bill(
            signup=self.guest_signup,
            report=self.report,
            prepaid_flights=0,
            amount=42,
            method=PaymentMethods.CASH,
        ).save()
        self.assertTrue(self.guest_signup.is_paid)

        with self.assertNumQueries(25):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": TODAY, "signup": self.guest_signup.pk},
                ),
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, f"{self.guest} hat bereits bezahlt.")

        with self.assertNumQueries(25):
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
        self.assertEqual(2, len(Bill.objects.all()))

    def test_signup_not_found_404(self):
        with self.assertNumQueries(6):
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
        with self.assertNumQueries(15):
            response = self.client.get(
                reverse("create_bill", kwargs={"date": TODAY, "signup": signup.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")


class BillUpdateViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            first_name="Orga", email="orga@example.com", role=get_user_model().Role.ORGA
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
            signup=self.signup, report=self.report, kind=Run.Kind.FLIGHT, created_on=now
        ).save()
        now += timedelta(hours=1)
        Run(
            signup=self.signup, report=self.report, kind=Run.Kind.FLIGHT, created_on=now
        ).save()
        now += timedelta(hours=1)
        Run(
            signup=self.signup, report=self.report, kind=Run.Kind.BOAT, created_on=now
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
        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_pilot_and_date_shown(self):
        with self.assertNumQueries(13):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_update.html")
        self.assertContains(response, self.orga)
        self.assertContains(
            response,
            TODAY.strftime("%a., %d. %b.").replace(" 0", " ").replace("..", "."),
        )

    def test_prepaid_flights_shown(self):
        with self.assertNumQueries(13):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_update.html")
        self.assertNotContains(response, "<td>Mit Abo bezahlt</td>")
        self.assertNotContains(response, "<td>Flüge gutgeschrieben</td>")
        self.assertContains(response, f'value="{self.bill.prepaid_flights}"')
        self.assertContains(response, f"<td>{self.bill.to_pay}</td>")

        self.bill.prepaid_flights = 1
        self.bill.save()
        with self.assertNumQueries(13):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_update.html")
        self.assertContains(response, "<td>Mit Abo bezahlt</td>")
        self.assertContains(response, f'value="{self.bill.prepaid_flights}"')
        self.assertContains(response, f"<td>{self.bill.prepaid_flights}</td>")
        self.assertContains(response, f"<td>{self.bill.to_pay}</td>")

        self.bill.prepaid_flights = -3
        self.bill.save()
        with self.assertNumQueries(13):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_update.html")
        self.assertNotContains(response, "<td>Mit Abo bezahlt</td>")
        self.assertContains(response, "<td>Flüge gutgeschrieben</td>")
        self.assertContains(response, f'value="{self.bill.prepaid_flights}"')
        self.assertContains(response, f"<td>{-self.bill.prepaid_flights}</td>")
        self.assertContains(response, f"<td>{self.bill.to_pay}</td>")

    def test_purchase_shown(self):
        with self.assertNumQueries(13):
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
        with self.assertNumQueries(13):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": self.bill.pk})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_update.html")
        self.assertContains(response, f'value="{self.bill.num_prepaid_flights}"')
        self.assertContains(response, f'value="{self.bill.amount}"')
        self.assertNotContains(response, "<td>Mit Abo bezahlt</td>")
        self.assertContains(
            response,
            f'value="{self.bill.method}" class="form-check-input" id="id_method_0" required checked',
        )
        self.assertNotContains(response, PaymentMethods.BANK_TRANSFER.label)

    def test_must_pay_enough(self):
        to_pay = Bill(signup=self.signup, report=self.report).to_pay
        with self.assertNumQueries(13):
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
        to_pay = Bill(signup=self.signup, report=self.report).to_pay + 5
        method = PaymentMethods.CASH
        with self.assertNumQueries(27):
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

    def test_update_bill_redirect_to_twint(self):
        to_pay = Bill(signup=self.signup, report=self.report).to_pay + 5
        method = PaymentMethods.TWINT
        with self.assertNumQueries(14):
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
        self.assertTemplateUsed(response, "bookkeeping/twint.html")
        self.assertContains(response, f"Bezahlung von {self.orga} gespeichert.")
        self.assertContains(response, f"Betrag Fr. {to_pay}")
        self.assertContains(response, reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(1, len(Bill.objects.all()))
        created_bill = Bill.objects.first()
        self.assertEqual(to_pay, created_bill.amount)
        self.assertEqual(method, created_bill.method)

    def test_delete_bill(self):
        with self.assertNumQueries(24):
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
        with self.assertNumQueries(6):
            response = self.client.get(
                reverse("update_bill", kwargs={"date": TODAY, "pk": 666})
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")


class PerformanceTests(TestCase):
    def setUp(self):
        num_pilots = randint(5, 10)
        num_days = randint(5, 10)
        num_flights = randint(5, 10)

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

        self.signups = []
        self.bills = []
        for i in range(num_days):
            training = Training.objects.create(date=TODAY - timedelta(days=i))
            report = Report.objects.create(training=training, cash_at_start=420)
            for pilot in pilots:
                signup = Signup.objects.create(pilot=pilot, training=training)
                self.signups.append(signup)
                for j in range(num_flights):
                    Run(
                        signup=signup,
                        report=report,
                        kind=Run.Kind.FLIGHT,
                        created_on=timezone.now() - timedelta(minutes=j),
                    ).save()
                Purchase.save_day_pass(signup=signup, report=report)
                bill = Bill.objects.create(
                    signup=signup,
                    report=report,
                    prepaid_flights=3,
                    amount=15,
                    method=PaymentMethods.TWINT,
                )
                self.bills.append(bill)
            training.select_signups()

    def test_bill_list_view(self):
        with self.assertNumQueries(11):
            response = self.client.get(reverse("bills"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_list.html")

    def test_pilot_list_view(self):
        with self.assertNumQueries(11):
            response = self.client.get(reverse("pilots"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/pilot_list.html")

    def test_bill_create_view(self):
        Bill.objects.all().delete()

        signup = self.signups[-1]
        with self.assertNumQueries(18):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": signup.training.date, "signup": signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")

        signup = self.signups[0]
        with self.assertNumQueries(19):
            response = self.client.get(
                reverse(
                    "create_bill",
                    kwargs={"date": signup.training.date, "signup": signup.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_create.html")

        with self.assertNumQueries(10):
            response = self.client.post(
                reverse(
                    "create_bill",
                    kwargs={"date": signup.training.date, "signup": signup.pk},
                ),
                data={
                    "prepaid_flights": 2,
                    "amount": 420,
                    "method": PaymentMethods.CASH,
                },
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

    def test_bill_update_view(self):
        bill = self.bills[3]
        with self.assertNumQueries(13):
            response = self.client.get(
                reverse(
                    "update_bill",
                    kwargs={"date": bill.signup.training.date, "pk": bill.pk},
                )
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/bill_update.html")

        with self.assertNumQueries(9):
            response = self.client.post(
                reverse(
                    "update_bill",
                    kwargs={"date": bill.signup.training.date, "pk": bill.pk},
                ),
                data={
                    "prepaid_flights": 0,
                    "amount": 420,
                    "method": PaymentMethods.CASH,
                },
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

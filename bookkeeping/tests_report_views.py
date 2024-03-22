from datetime import timedelta
from itertools import product
from http import HTTPStatus
from random import randint
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Absorption, Bill, Expense, PaymentMethods, Report, Run
from trainings.models import Purchase, Signup, Training


TODAY = timezone.now().date()
YESTERDAY = TODAY - timedelta(days=1)


class ReportListViewTests(TestCase):
    def setUp(self):
        orga = get_user_model().objects.create(
            email="orga@example.com", role=get_user_model().Role.ORGA
        )
        self.client.force_login(orga)

        self.training = Training.objects.create(date=TODAY)
        signup = Signup.objects.create(pilot=orga, training=self.training)
        self.report = Report.objects.create(
            training=self.training, cash_at_start=1337, remarks="Some remarks."
        )
        self.cash_bill = Bill.objects.create(
            signup=signup,
            report=self.report,
            prepaid_flights=0,
            amount=420,
            method=PaymentMethods.CASH,
        )
        self.guest = get_user_model().objects.create(email="guest@example.com")
        signup = Signup.objects.create(pilot=self.guest, training=self.training)
        for i in range(3):
            Run(
                signup=signup,
                report=self.report,
                kind=Run.Kind.FLIGHT,
                created_on=timezone.now() - timedelta(minutes=i),
            ).save()
        self.twint_bill = Bill.objects.create(
            signup=signup,
            report=self.report,
            prepaid_flights=0,
            amount=420,
            method=PaymentMethods.TWINT,
        )
        self.expense = Expense.objects.create(
            report=self.report, reason="Gas", amount=13
        )
        self.training.select_signups()

    def test_orga_required_to_see(self):
        self.client.force_login(self.guest)
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_orga_required_to_see_menu(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, reverse("reports"))

        self.client.force_login(self.guest)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertNotContains(response, reverse("reports") + '"')

    def test_pagination_by_year(self):
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertNotContains(
            response, reverse("reports", kwargs={"year": TODAY.year + 1})
        )
        self.assertNotContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 1})
        )

        for date in [
            YESTERDAY,
            TODAY - timedelta(days=365),
            TODAY - 3 * timedelta(days=365),
        ]:
            training = Training.objects.create(date=date)
            Report(training=training, cash_at_start=1337).save()

        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 1})
        )
        self.assertNotContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 2})
        )
        self.assertNotContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 3})
        )

        response = self.client.get(reverse("reports", kwargs={"year": TODAY.year - 1}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertContains(response, reverse("reports", kwargs={"year": TODAY.year}))
        self.assertNotContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 2})
        )
        self.assertContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 3})
        )

        response = self.client.get(reverse("reports", kwargs={"year": TODAY.year - 3}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertNotContains(
            response, reverse("reports", kwargs={"year": TODAY.year})
        )
        self.assertContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 1})
        )
        self.assertNotContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 4})
        )

    def test_num_runs_shown(self):
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertContains(response, f"<td>{self.report.num_runs}</td>")

    def test_difference_between_reports(self):
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertContains(response, "❓")

        difference_between_reports = 420
        training = Training.objects.create(date=YESTERDAY)
        Report(
            training=training,
            cash_at_start=1,
            cash_at_end=self.report.cash_at_start - difference_between_reports,
        ).save()
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertContains(
            response, f"{self.report.cash_at_start} ({difference_between_reports})"
        )

    def test_revenue_shown(self):
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertContains(response, self.cash_bill.amount)
        self.assertContains(response, self.twint_bill.amount)

    def test_expenses_shown(self):
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertContains(response, self.expense.amount)

    def test_difference_within_report_shown(self):
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertContains(response, "❓")

        difference_within_report = 666
        self.report.cash_at_end = (
            self.report.cash_at_start
            + self.cash_bill.amount
            - self.expense.amount
            + difference_within_report
        )
        self.report.save()
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertContains(
            response, f"{self.report.cash_at_end} ({difference_within_report})"
        )

    def test_num_unpaid_signups_shown(self):
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertContains(
            response,
            f"{self.report.num_unpaid_signups} / {len(self.training.selected_signups)}",
        )

    def test_remarks_shown(self):
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertContains(response, self.report.remarks)

    def test_no_reports_in_year_404(self):
        response = self.client.get(reverse("reports", kwargs={"year": 1984}))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        Report.objects.all().delete()
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        training = Training.objects.create(date=TODAY - timedelta(days=365))
        Report(training=training, cash_at_start=1337).save()
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertNotContains(response, TODAY.year)


class BalanceViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            email="orga@example.com", first_name="Orga", role=get_user_model().Role.ORGA
        )
        self.client.force_login(self.orga)

        self.training = Training.objects.create(date=TODAY)
        orga_signup = Signup.objects.create(pilot=self.orga, training=self.training)
        self.first_report = Report.objects.create(
            training=self.training,
            cash_at_start=420,
            cash_at_end=666,
            remarks="Some remarks.",
        )
        self.day_pass = Purchase.save_day_pass(
            signup=orga_signup, report=self.first_report
        )
        self.prepaid_flights = Purchase.save_item(
            signup=orga_signup,
            report=self.first_report,
            choice=Purchase.Items.PREPAID_FLIGHTS,
        )
        self.cash_bill = Bill.objects.create(
            signup=orga_signup,
            report=self.first_report,
            prepaid_flights=0,
            amount=self.day_pass.price + self.prepaid_flights.price,
            method=PaymentMethods.CASH,
        )

        self.guest = get_user_model().objects.create(
            email="guest@example.com", first_name="Guest"
        )
        guest_signup = Signup.objects.create(pilot=self.guest, training=self.training)
        self.life_jacket = Purchase.save_item(
            signup=guest_signup,
            report=self.first_report,
            choice=Purchase.Items.LIFEJACKET,
        )
        self.rearming_kit = Purchase.save_item(
            signup=guest_signup,
            report=self.first_report,
            choice=Purchase.Items.REARMING_KIT,
        )
        self.twint_bill = Bill.objects.create(
            signup=guest_signup,
            report=self.first_report,
            prepaid_flights=0,
            amount=self.life_jacket.price + self.rearming_kit.price,
            method=PaymentMethods.TWINT,
        )

        self.first_gas = Expense.objects.create(
            report=self.first_report, reason="Gas", amount=87
        )
        self.second_gas = Expense.objects.create(
            report=self.first_report, reason="Gas", amount=25
        )
        self.other_expense = Expense.objects.create(
            report=self.first_report, reason="other", amount=25
        )
        self.bank_absorption = Absorption.objects.create(
            report=self.first_report,
            signup=orga_signup,
            amount=83,
            method=PaymentMethods.BANK_TRANSFER,
        )
        self.zero_absorption = Absorption.objects.create(
            report=self.first_report,
            signup=guest_signup,
            amount=0,
            method=PaymentMethods.TWINT,
        )

        later_training = Training.objects.create(date=TODAY + timedelta(days=10))
        orga_signup = Signup.objects.create(pilot=self.orga, training=later_training)
        self.last_report = Report.objects.create(
            training=later_training,
            cash_at_start=666,
            cash_at_end=1337,
            remarks="Some remarks.",
        )
        self.twint_absorption = Absorption.objects.create(
            report=self.last_report,
            signup=orga_signup,
            amount=39,
            method=PaymentMethods.TWINT,
        )

    def test_orga_required_to_see(self):
        self.client.force_login(self.guest)
        response = self.client.get(reverse("balance"))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_orga_required_to_see_menu(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, reverse("balance"))

        self.client.force_login(self.guest)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertNotContains(response, reverse("balance") + '"')

    def test_pagination_by_year(self):
        response = self.client.get(reverse("balance"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_balance.html")
        self.assertNotContains(
            response, reverse("balance", kwargs={"year": TODAY.year + 1})
        )
        self.assertNotContains(
            response, reverse("balance", kwargs={"year": TODAY.year - 1})
        )

        for date in [
            YESTERDAY,
            TODAY - timedelta(days=365),
            TODAY - 3 * timedelta(days=365),
        ]:
            training = Training.objects.create(date=date)
            Report(training=training, cash_at_start=1337).save()

        response = self.client.get(reverse("balance"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_balance.html")
        self.assertContains(response, reverse("reports", kwargs={"year": TODAY.year}))
        self.assertContains(
            response, reverse("balance", kwargs={"year": TODAY.year - 1})
        )
        self.assertNotContains(
            response, reverse("balance", kwargs={"year": TODAY.year - 2})
        )
        self.assertNotContains(
            response, reverse("balance", kwargs={"year": TODAY.year - 3})
        )

        response = self.client.get(reverse("balance", kwargs={"year": TODAY.year - 1}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_balance.html")
        self.assertContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 1})
        )
        self.assertContains(response, reverse("balance", kwargs={"year": TODAY.year}))
        self.assertNotContains(
            response, reverse("balance", kwargs={"year": TODAY.year - 2})
        )
        self.assertContains(
            response, reverse("balance", kwargs={"year": TODAY.year - 3})
        )

        response = self.client.get(reverse("balance", kwargs={"year": TODAY.year - 3}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_balance.html")
        self.assertContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 3})
        )
        self.assertNotContains(
            response, reverse("balance", kwargs={"year": TODAY.year})
        )
        self.assertContains(
            response, reverse("balance", kwargs={"year": TODAY.year - 1})
        )
        self.assertNotContains(
            response, reverse("balance", kwargs={"year": TODAY.year - 4})
        )

    def test_first_and_latest_cash(self):
        response = self.client.get(reverse("balance"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_balance.html")
        self.assertContains(response, self.first_report.cash_at_start)
        total_difference = self.first_report.difference + self.last_report.difference
        self.assertContains(
            response, f"{self.last_report.cash_at_end} ({total_difference})"
        )
        self.assertContains(response, reverse("reports"))

    def test_purchases_added_up(self):
        response = self.client.get(reverse("balance"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_balance.html")

        self.assertContains(response, PaymentMethods.CASH.label)
        self.assertContains(response, self.day_pass.price)
        self.assertContains(response, self.prepaid_flights.price)
        self.assertContains(response, self.cash_bill.amount)

        self.assertContains(response, PaymentMethods.TWINT.label)
        self.assertContains(response, self.life_jacket.price + self.rearming_kit.price)
        self.assertContains(response, self.twint_bill.amount)

    def test_twint_absorption_is_revenue(self):
        response = self.client.get(reverse("balance"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_balance.html")
        self.assertContains(
            response, self.twint_absorption.amount + self.twint_bill.amount
        )

    def test_expeditures_shown(self):
        response = self.client.get(reverse("balance"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_balance.html")

        self.assertContains(response, self.first_gas.amount + self.second_gas.amount)
        self.assertContains(response, self.other_expense.amount)
        self.assertContains(
            response,
            self.first_gas.amount
            + self.second_gas.amount
            + self.other_expense.amount
            + self.bank_absorption.amount
            + self.twint_absorption.amount,
        )

        self.assertContains(response, self.first_gas.amount)
        self.assertContains(response, self.first_gas.reason)
        self.assertContains(response, self.second_gas.amount)
        self.assertContains(response, self.other_expense.amount)
        self.assertContains(response, self.other_expense.reason)

    def test_non_zero_transactions_shown(self):
        response = self.client.get(reverse("balance"))
        self.assertContains(response, PaymentMethods.BANK_TRANSFER.label)
        self.assertContains(response, self.bank_absorption.amount)
        self.assertContains(response, self.bank_absorption.description)

        self.assertContains(response, PaymentMethods.TWINT.label)
        self.assertContains(response, self.twint_bill.amount)
        self.assertContains(response, self.twint_bill.description)

        self.assertNotContains(response, self.zero_absorption.description)

    def test_twint_totals_by_week(self):
        response = self.client.get(reverse("balance"))
        twint_date = self.twint_bill.signup.training.date
        monday = twint_date - timedelta(days=twint_date.weekday())
        self.assertContains(
            response, monday.strftime("%d.%m.").lstrip("0").replace(".0", ".")
        )
        sunday = twint_date + timedelta(days=6 - twint_date.weekday())
        self.assertContains(
            response, sunday.strftime("%d.%m.").lstrip("0").replace(".0", ".")
        )
        self.assertContains(response, f"Total {self.twint_bill.amount}")

        twint_date = self.twint_absorption.report.training.date
        monday = twint_date - timedelta(days=twint_date.weekday())
        self.assertContains(
            response, monday.strftime("%d.%m.").lstrip("0").replace(".0", ".")
        )
        sunday = twint_date + timedelta(days=6 - twint_date.weekday())
        self.assertContains(
            response, sunday.strftime("%d.%m.").lstrip("0").replace(".0", ".")
        )
        self.assertContains(response, f"Total {self.twint_absorption.amount}")

    def test_no_reports_in_year_404(self):
        response = self.client.get(reverse("balance", kwargs={"year": 1984}))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        Report.objects.all().delete()
        response = self.client.get(reverse("balance"))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        training = Training.objects.create(date=TODAY - timedelta(days=365))
        Report(training=training, cash_at_start=1337).save()
        response = self.client.get(reverse("balance"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_balance.html")
        self.assertNotContains(response, TODAY.year)


class ReportCreateViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            email="orga@example.com", first_name="Orga", role=get_user_model().Role.ORGA
        )
        self.client.force_login(self.orga)

    def test_orga_required_to_see(self):
        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        response = self.client.get(reverse("create_report"))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_existing_training_required(self):
        response = self.client.get(reverse("create_report"))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        Training(date=TODAY, emergency_mail_sender=self.orga).save()
        response = self.client.get(reverse("create_report"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_create.html")

    def test_only_in_menu_if_training_exists(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertNotContains(response, reverse("create_report"))

        Training(date=TODAY).save()
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, reverse("create_report"))

    def test_redirect_to_emergency_mail(self):
        Training(date=TODAY).save()
        response = self.client.get(reverse("create_report"), follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertTrue(
            reverse("create_report").replace("/", "%2F")
            in response.request["QUERY_STRING"]
        )

    def test_briefing_checkbox_shown(self):
        training = Training.objects.create(date=TODAY, emergency_mail_sender=self.orga)
        pilot = get_user_model().objects.create(
            email="pilot_a@example.com", first_name="Name A"
        )
        Signup(training=training, pilot=pilot).save()
        response = self.client.get(reverse("create_report"), follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_create.html")
        self.assertContains(response, "Briefing mit Name A durchgeführt.")

        pilot = get_user_model().objects.create(
            email="pilot_b@example.com", first_name="Name B"
        )
        Signup(training=training, pilot=pilot).save()
        response = self.client.get(reverse("create_report"), follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_create.html")
        self.assertContains(response, "Briefing mit Name A und Name B durchgeführt.")

        pilot = get_user_model().objects.create(
            email="pilot_c@example.com", first_name="Name C"
        )
        Signup(training=training, pilot=pilot).save()
        response = self.client.get(reverse("create_report"), follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_create.html")
        self.assertContains(
            response, "Briefing mit Name A, Name B und Name C durchgeführt."
        )

    def test_only_positive_integers_allowed_for_cash(self):
        Training(date=TODAY).save()
        response = self.client.post(
            reverse("create_report"), data={"cash_at_start": -666}, follow=True
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_create.html")
        self.assertEqual(0, len(Report.objects.all()))

    def test_create_report(self):
        training = Training.objects.create(date=TODAY)
        pilot = get_user_model().objects.create(
            email="pilot_a@example.com", first_name="Name A"
        )
        Signup(training=training, pilot=pilot).save()
        response = self.client.post(
            reverse("create_report"),
            data={
                "cash_at_start": 1337,
                "sufficient_parking_tickets": True,
                "briefing": True,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertNotContains(
            response, "Bitte im Tourismusbüro neue Parkkarten besorgen."
        )
        self.assertNotContains(
            response, "Bitte Briefing vor dem ersten Flug durchführen."
        )
        self.assertEqual(1, len(Report.objects.all()))
        created_report = Report.objects.first()
        self.assertEqual(1337, created_report.cash_at_start)

    def test_create_report_with_parking_ticket_warning(self):
        Training(date=TODAY).save()
        response = self.client.post(
            reverse("create_report"),
            data={"cash_at_start": 1337, "sufficient_parking_tickets": False},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(
            response, "Bitte im Tourismusbüro neue Parkkarten besorgen."
        )
        self.assertEqual(1, len(Report.objects.all()))
        created_report = Report.objects.first()
        self.assertEqual(1337, created_report.cash_at_start)

    def test_create_report_with_briefing_warning(self):
        training = Training.objects.create(date=TODAY)
        pilot = get_user_model().objects.create(
            email="pilot_a@example.com", first_name="Name A"
        )
        Signup(training=training, pilot=pilot).save()
        response = self.client.post(
            reverse("create_report"),
            data={"cash_at_start": 1337, "briefing": False},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, "Bitte Briefing vor dem ersten Flug durchführen.")
        self.assertEqual(1, len(Report.objects.all()))
        created_report = Report.objects.first()
        self.assertEqual(1337, created_report.cash_at_start)

    @mock.patch("bookkeeping.views.timezone")
    def test_redirect_to_existing_report(self, mocked_timezone):
        training = Training.objects.create(date=YESTERDAY)
        report = Report.objects.create(training=training, cash_at_start=1337)
        mocked_timezone.now.return_value = timezone.now() - timedelta(days=1)
        mocked_timezone.localtime.return_value = timezone.localtime() - timedelta(
            days=1
        )

        response = self.client.get(reverse("create_report"), follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")

        response = self.client.post(
            reverse("create_report"), data={"cash_at_start": 666}, follow=True
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertEqual(1, len(Report.objects.all()))
        report.refresh_from_db()
        self.assertEqual(1337, report.cash_at_start)


class ReportUpdateViewTests(TestCase):
    def setUp(self):
        orga = get_user_model().objects.create(
            first_name="Orga", email="orga@example.com", role=get_user_model().Role.ORGA
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

        self.report = Report.objects.create(
            training=training, cash_at_start=1337, remarks="Some remarks."
        )
        Run(
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.FLIGHT,
            created_on=timezone.now() - timedelta(minutes=10),
        ).save()

    def test_orga_required_to_see(self):
        self.client.force_login(self.guest)
        response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_get_update_report_selects_signups(self):
        for signup in Signup.objects.all():
            signup.refresh_from_db()
            self.assertEqual(signup.status, Signup.Status.WAITING)

        response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)

        for signup in Signup.objects.all():
            self.assertEqual(signup.status, Signup.Status.SELECTED)

    def test_form_is_prefilled(self):
        response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, self.report.cash_at_start)
        self.assertContains(response, self.report.remarks)

    def test_links_to_pay_shown(self):
        bill = Bill.objects.create(
            signup=self.orga_signup,
            report=self.report,
            prepaid_flights=0,
            amount=420,
            method=PaymentMethods.CASH,
        )
        response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(
            response,
            reverse(
                "create_bill", kwargs={"date": TODAY, "signup": self.guest_signup.pk}
            ),
        )
        self.assertContains(
            response,
            reverse("update_bill", kwargs={"date": TODAY, "pk": bill.pk}),
        )

    def test_revenue_shown(self):
        bill = Bill.objects.create(
            signup=self.orga_signup,
            report=self.report,
            prepaid_flights=0,
            amount=420,
            method=PaymentMethods.CASH,
        )
        response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, bill.amount)

    def test_expense_shown(self):
        expense = Expense.objects.create(report=self.report, reason="Gas", amount=13)
        response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, expense.reason)
        self.assertContains(response, expense.amount)
        self.assertContains(
            response,
            reverse("update_expense", kwargs={"date": TODAY, "pk": expense.pk}),
        )

    def test_training_orgas_shown(self):
        response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, "Noch keine.")

        self.report.orga_1 = self.orga_signup
        self.report.save()
        response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, f"<li>{self.orga_signup.pilot}</li>")

    def test_only_positive_integers_allowed_for_cash(self):
        response = self.client.post(
            reverse("update_report", kwargs={"date": TODAY}),
            data={"cash_at_start": -666, "cash_at_end": -666},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")

        self.report.refresh_from_db()
        self.assertEqual(1337, self.report.cash_at_start)
        self.assertNotEqual(-666, self.report.cash_at_end)

    def test_create_run_button_only_shown_on_training_day(self):
        response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, reverse("create_run"))

        training = Training.objects.create(date=YESTERDAY)
        Report(training=training, cash_at_start=1337).save()
        response = self.client.get(reverse("update_report", kwargs={"date": YESTERDAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertNotContains(response, reverse("create_run"))

    def test_update_run_buttons_only_shown_on_training_day(self):
        response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, reverse("update_run", kwargs={"run": 1}))
        self.assertContains(response, "bi bi-pencil-square")

        training = Training.objects.create(date=YESTERDAY)
        report = Report.objects.create(training=training, cash_at_start=1337)
        Run(
            signup=self.guest_signup,
            report=report,
            kind=Run.Kind.FLIGHT,
            created_on=timezone.now() - timedelta(minutes=20),
        ).save()
        response = self.client.get(reverse("update_report", kwargs={"date": YESTERDAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertNotContains(response, reverse("update_run", kwargs={"run": 1}))
        self.assertNotContains(response, "bi bi-pencil-square")

    def test_create_expense_button_always_shown(self):
        response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, reverse("create_expense", kwargs={"date": TODAY}))
        self.assertNotContains(
            response, reverse("create_expense", kwargs={"date": YESTERDAY})
        )

        training = Training.objects.create(date=YESTERDAY)
        Report(training=training, cash_at_start=1337).save()
        response = self.client.get(reverse("update_report", kwargs={"date": YESTERDAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(
            response, reverse("create_expense", kwargs={"date": YESTERDAY})
        )
        self.assertNotContains(
            response, reverse("create_expense", kwargs={"date": TODAY})
        )

    def test_pilots_listed_alphabetically(self):
        response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        response_after_guest = str(response.content).split("Guest")[-1]
        self.assertTrue("Orga" in response_after_guest)

    def test_list_of_runs_with_signup_not_in_every_run(self):
        Run(
            signup=self.orga_signup,
            report=self.report,
            kind=Run.Kind.FLIGHT,
            created_on=timezone.now(),
        ).save()

        response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        guest_row = (
            response.content.decode(response.charset)
            .split("Guest")[1]
            .split("</tr>")[0]
            .replace(" ", "")
            .replace("\n", "")
        )
        self.assertTrue(guest_row.endswith("<td>🪂</td><td>❌</td>"))
        orga_row = (
            response.content.decode(response.charset)
            .split("Orga")[1]
            .split("</tr>")[0]
            .replace(" ", "")
            .replace("\n", "")
        )
        self.assertTrue(orga_row.endswith("<td>❌</td><td>🪂</td>"))

    def test_update_report(self):
        Bill(
            signup=self.orga_signup,
            report=self.report,
            prepaid_flights=0,
            amount=10,
            method=PaymentMethods.CASH,
        ).save()
        Bill(
            signup=self.guest_signup,
            report=self.report,
            prepaid_flights=0,
            amount=2,
            method=PaymentMethods.CASH,
        ).save()
        cash_at_end = 2000
        new_remarks = "Some new remarks"
        response = self.client.post(
            reverse("update_report", kwargs={"date": TODAY}),
            data={
                "cash_at_start": self.report.cash_at_start,
                "cash_at_end": cash_at_end,
                "remarks": new_remarks,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.report.refresh_from_db()
        self.assertEqual(self.report.cash_at_end, cash_at_end)
        self.assertEqual(self.report.remarks, new_remarks)
        self.assertNotContains(response, "Es haben noch nicht alle bezahlt.")
        self.assertNotContains(response, "Bitte Kassenstand erfassen.")
        self.assertNotContains(response, "Zu wenig Geld in der Kasse.")

    def test_everyone_paid_warnings_not_enough_cash_warnings(self):
        response = self.client.post(
            reverse("update_report", kwargs={"date": TODAY}),
            data={
                "cash_at_start": self.report.cash_at_start,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, "Es haben noch nicht alle bezahlt.")
        self.assertNotContains(response, "Bitte Kassenstand erfassen.")
        self.assertNotContains(response, "Zu wenig Geld in der Kasse.")
        self.assertContains(
            response,
            '<button class="btn btn-secondary" type="submit">Kasse Speichern</button>',
        )

        expense = Expense.objects.create(report=self.report, reason="Gas", amount=35)
        bill_1 = Bill.objects.create(
            signup=self.orga_signup,
            report=self.report,
            prepaid_flights=0,
            amount=75,
            method=PaymentMethods.CASH,
        )
        bill_2 = Bill.objects.create(
            signup=self.guest_signup,
            report=self.report,
            prepaid_flights=0,
            amount=20,
            method=PaymentMethods.CASH,
        )
        response = self.client.post(
            reverse("update_report", kwargs={"date": TODAY}),
            data={
                "cash_at_start": self.report.cash_at_start,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertNotContains(response, "Es haben noch nicht alle bezahlt.")
        self.assertContains(response, "Bitte Kassenstand erfassen.")
        self.assertNotContains(response, "Zu wenig Geld in der Kasse.")
        self.assertContains(
            response,
            '<button class="btn btn-secondary" type="submit">Kasse Speichern</button>',
        )

        response = self.client.post(
            reverse("update_report", kwargs={"date": TODAY}),
            data={
                "cash_at_start": self.report.cash_at_start,
                "cash_at_end": self.report.cash_at_start - 1,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertNotContains(response, "Es haben noch nicht alle bezahlt.")
        self.assertNotContains(response, "Bitte Kassenstand erfassen.")
        self.assertContains(response, "Zu wenig Geld in der Kasse.")
        self.assertContains(
            response,
            '<button class="btn btn-primary" type="submit">Kasse Speichern</button>',
        )

        response = self.client.post(
            reverse("update_report", kwargs={"date": TODAY}),
            data={
                "cash_at_start": self.report.cash_at_start,
                "cash_at_end": (
                    self.report.cash_at_start
                    - expense.amount
                    + bill_1.amount
                    + bill_2.amount
                ),
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")
        self.assertNotContains(response, "Es haben noch nicht alle bezahlt.")
        self.assertNotContains(response, "Bitte Kassenstand erfassen.")
        self.assertNotContains(response, "Zu wenig Geld in der Kasse.")
        self.assertContains(
            response, "Alle haben bezahlt und der Kassenstand ist gespeichert 😊"
        )

    @mock.patch("bookkeeping.views.timezone")
    def test_warning_when_finishing_early(self, mocked_timezone):
        Run.objects.all().delete()
        training = Training.objects.create(date=YESTERDAY)
        Report(training=training, cash_at_start=420).save()

        for training_date, hours in product([YESTERDAY, TODAY], [16, 17]):
            with self.subTest(training_date=training_date, hours=hours):
                mocked_timezone.localtime.return_value = (
                    timezone.datetime.fromisoformat(f"{TODAY} {hours}:05:00")
                )
                response = self.client.post(
                    reverse("update_report", kwargs={"date": training_date}),
                    data={
                        "cash_at_start": self.report.cash_at_start,
                        "cash_at_end": self.report.cash_at_start,
                    },
                    follow=True,
                )
                self.assertEqual(response.status_code, HTTPStatus.OK)
                if training_date == TODAY and hours < 17:
                    self.assertContains(
                        response,
                        "Falls das Training frühzeitig abgebrochen wurde, sollte insbesondere bei starkem "
                        'Wind die Seelpolizei unter <a href="tel:+41316387676">+41 31 638 76 76</a> '
                        "benachrichtigt werden, dass unser Boot nicht mehr vor Ort ist.",
                    )
                else:
                    self.assertNotContains(
                        response,
                        "Falls das Training frühzeitig abgebrochen wurde, sollte insbesondere bei starkem "
                        'Wind die Seelpolizei unter <a href="tel:+41316387676">+41 31 638 76 76</a> '
                        "benachrichtigt werden, dass unser Boot nicht mehr vor Ort ist.",
                    )

    def test_report_not_found_404(self):
        response = self.client.get(reverse("update_report", kwargs={"date": YESTERDAY}))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")


class DatabaseCallsTests(TestCase):
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
        for i in range(num_days):
            training = Training.objects.create(
                date=TODAY - timedelta(days=i), emergency_mail_sender=orga
            )
            report = Report.objects.create(training=training, cash_at_start=420)
            now = timezone.now() - timedelta(days=i)
            for pilot in pilots:
                signup = Signup.objects.create(pilot=pilot, training=training)
                for j in range(num_flights):
                    created_on = now + timedelta(minutes=j)
                    Run(
                        signup=signup,
                        report=report,
                        kind=Run.Kind.FLIGHT,
                        created_on=created_on,
                    ).save()
                Purchase.save_day_pass(signup=signup, report=report)
                Bill(
                    signup=signup,
                    report=report,
                    prepaid_flights=3,
                    amount=15,
                    method=PaymentMethods.TWINT,
                ).save()
            Expense(report=report, reason="Gas", amount=11).save()
            Absorption(
                report=report, signup=signup, amount=15, method=PaymentMethods.CASH
            ).save()
            training.select_signups()

    def test_report_list_view(self):
        with self.assertNumQueries(17):
            response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_list.html")

    def test_balance_view(self):
        with self.assertNumQueries(20):
            response = self.client.get(reverse("balance"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_balance.html")

    def test_report_create_view(self):
        training = Training.objects.filter(date=TODAY)[0]
        Report.objects.filter(training=training).delete()

        with self.assertNumQueries(13):
            response = self.client.get(reverse("create_report"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_create.html")

        with self.assertNumQueries(12):
            response = self.client.post(
                reverse("create_report"), data={"cash_at_start": 420}, follow=False
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertTrue(Report.objects.filter(training=training).exists())

    def test_report_update_view(self):
        with self.assertNumQueries(15):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")

        with self.assertNumQueries(14):
            response = self.client.post(
                reverse("update_report", kwargs={"date": TODAY}),
                data={
                    "cash_at_start": 1337,
                    "cash_at_end": 420,
                    "remarks": "Some remarks",
                },
                follow=False,
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

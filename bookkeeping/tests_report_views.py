from datetime import date, timedelta
from http import HTTPStatus
import locale

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Bill, Expense, Report, Run
from trainings.models import Signup, Training

locale.setlocale(locale.LC_TIME, "de_CH")

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


class ReportListViewTests(TestCase):
    def setUp(self):
        orga = get_user_model().objects.create(
            email="orga@example.com", role=get_user_model().Role.Orga
        )
        self.client.force_login(orga)

        training = Training.objects.create(date=TODAY)
        signup = Signup.objects.create(pilot=orga, training=training)
        self.report = Report.objects.create(training=training, cash_at_start=1337)
        self.bill = Bill.objects.create(signup=signup, report=self.report, payed=420)
        self.expense = Expense.objects.create(
            report=self.report, reason="Gas", amount=13
        )

    def test_orga_required_to_see(self):
        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        with self.assertNumQueries(2):
            response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_orga_required_to_see_menu(self):
        with self.assertNumQueries(4):
            response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, reverse("reports"))

        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        with self.assertNumQueries(3):
            response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertNotContains(response, reverse("reports"))

    def test_pagination_by_year(self):
        with self.assertNumQueries(8):
            response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/list_reports.html")
        self.assertNotContains(
            response, reverse("reports", kwargs={"year": TODAY.year + 1})
        )
        self.assertNotContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 1})
        )

        for date in [
            YESTERDAY,
            TODAY - timedelta(days=365),
            TODAY - 2 * timedelta(days=365),
        ]:
            training = Training.objects.create(date=date)
            Report(training=training, cash_at_start=1337).save()

        with self.assertNumQueries(8):
            response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/list_reports.html")
        self.assertContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 1})
        )
        self.assertNotContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 2})
        )

        with self.assertNumQueries(7):
            response = self.client.get(
                reverse("reports", kwargs={"year": TODAY.year - 1})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/list_reports.html")
        self.assertContains(response, reverse("reports", kwargs={"year": TODAY.year}))
        self.assertContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 2})
        )

        with self.assertNumQueries(7):
            response = self.client.get(
                reverse("reports", kwargs={"year": TODAY.year - 2})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/list_reports.html")
        self.assertNotContains(
            response, reverse("reports", kwargs={"year": TODAY.year})
        )
        self.assertContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 1})
        )
        self.assertNotContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 3})
        )

    def test_difference_between_reports(self):
        difference_between_reports = 420
        training = Training.objects.create(date=YESTERDAY)
        Report(
            training=training,
            cash_at_start=1,
            cash_at_end=self.report.cash_at_start - difference_between_reports,
        ).save()

        with self.assertNumQueries(8):
            response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/list_reports.html")
        self.assertContains(response, difference_between_reports)

    def test_revenue_shown(self):
        with self.assertNumQueries(8):
            response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/list_reports.html")
        self.assertContains(response, self.bill.payed)

    def test_expenses_shown(self):
        with self.assertNumQueries(8):
            response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/list_reports.html")
        self.assertContains(response, self.expense.amount)

    def test_difference_within_report_shown(self):
        difference_within_report = 666
        self.report.cash_at_end = (
            self.report.cash_at_start
            + self.bill.payed
            - self.expense.amount
            + difference_within_report
        )
        self.report.save()
        with self.assertNumQueries(8):
            response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/list_reports.html")
        self.assertContains(response, difference_within_report)

    def test_no_reports_in_year_404(self):
        with self.assertNumQueries(4):
            response = self.client.get(reverse("reports", kwargs={"year": 1984}))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        Report.objects.all().delete()
        with self.assertNumQueries(4):
            response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        training = Training.objects.create(date=TODAY - timedelta(days=365))
        Report(training=training, cash_at_start=1337).save()
        with self.assertNumQueries(8):
            response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/list_reports.html")
        self.assertNotContains(response, TODAY.year)


class ReportCreateViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            email="orga@example.com", role=get_user_model().Role.Orga
        )
        self.client.force_login(self.orga)

    def test_orga_required_to_see(self):
        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        with self.assertNumQueries(2):
            response = self.client.get(reverse("create_report"))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_existing_training_required(self):
        with self.assertNumQueries(4):
            response = self.client.get(reverse("create_report"))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        Training(date=TODAY).save()
        with self.assertNumQueries(5):
            response = self.client.get(reverse("create_report"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_report.html")

    def test_only_in_menu_if_training_exists(self):
        with self.assertNumQueries(4):
            response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertNotContains(response, reverse("create_report"))

        Training(date=TODAY).save()
        with self.assertNumQueries(4):
            response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, reverse("create_report"))

    def test_only_positive_integers_allowed_for_cash(self):
        Training(date=TODAY).save()
        with self.assertNumQueries(3):
            response = self.client.post(
                reverse("create_report"), data={"cash_at_start": -666}, follow=True
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_report.html")
        self.assertEqual(0, len(Report.objects.all()))

    def test_create_report(self):
        Training(date=TODAY).save()
        with self.assertNumQueries(17):
            response = self.client.post(
                reverse("create_report"), data={"cash_at_start": 1337}, follow=True
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertEqual(1, len(Report.objects.all()))
        created_report = Report.objects.first()
        self.assertEqual(1337, created_report.cash_at_start)

    def test_redirect_to_existing_report(self):
        training = Training.objects.create(date=TODAY)
        report = Report.objects.create(training=training, cash_at_start=1337)
        with self.assertNumQueries(15):
            response = self.client.get(reverse("create_report"), follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")

        with self.assertNumQueries(15):
            response = self.client.post(
                reverse("create_report"), data={"cash_at_start": 666}, follow=True
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertEqual(1, len(Report.objects.all()))
        report.refresh_from_db()
        self.assertEqual(1337, report.cash_at_start)


class ReportUpdateViewTests(TestCase):
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

    def test_orga_required_to_see(self):
        self.client.force_login(self.guest)
        with self.assertNumQueries(2):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_get_update_report_selects_signups(self):
        for signup in Signup.objects.all():
            self.assertEqual(signup.status, Signup.Status.Waiting)

        with self.assertNumQueries(19):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)

        for signup in Signup.objects.all():
            self.assertEqual(signup.status, Signup.Status.Selected)

    def test_form_is_prefilled(self):
        with self.assertNumQueries(19):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(response, self.report.cash_at_start)

    def test_links_to_pay_shown(self):
        Bill(signup=self.orga_signup, report=self.report, payed=420).save()
        with self.assertNumQueries(19):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(
            response,
            reverse("create_bill", kwargs={"signup": self.guest_signup.pk}),
        )
        self.assertNotContains(
            response,
            reverse("create_bill", kwargs={"signup": self.orga_signup.pk}),
        )

    def test_revenue_shown(self):
        bill = Bill.objects.create(
            signup=self.orga_signup, report=self.report, payed=420
        )
        with self.assertNumQueries(19):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(response, bill.payed)

    def test_expense_shown(self):
        expense = Expense.objects.create(report=self.report, reason="Gas", amount=13)
        with self.assertNumQueries(19):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(response, expense.reason)
        self.assertContains(response, expense.amount)
        self.assertContains(
            response,
            reverse("update_expense", kwargs={"date": TODAY, "expense": expense.pk}),
        )

    def test_only_positive_integers_allowed_for_cash(self):
        with self.assertNumQueries(19):
            response = self.client.post(
                reverse("update_report", kwargs={"date": TODAY}),
                data={"cash_at_start": -666, "cash_at_end": -666},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")

        self.report.refresh_from_db()
        self.assertEqual(1337, self.report.cash_at_start)
        self.assertNotEqual(-666, self.report.cash_at_end)

    def test_create_run_button_only_shown_on_training_day(self):
        with self.assertNumQueries(19):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(response, reverse("create_run"))
        self.assertContains(response, "bi bi-plus-square")

        training = Training.objects.create(date=YESTERDAY)
        Report(training=training, cash_at_start=1337).save()
        with self.assertNumQueries(11):
            response = self.client.get(
                reverse("update_report", kwargs={"date": YESTERDAY})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertNotContains(response, reverse("create_run"))
        self.assertNotContains(response, "bi bi-plus-square")

    def test_update_run_buttons_only_shown_on_training_day(self):
        Run(
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.Flight,
            created_on=timezone.now() - timedelta(minutes=10),
        ).save()
        with self.assertNumQueries(20):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(response, reverse("update_run", kwargs={"run": 1}))
        self.assertContains(response, "bi bi-pencil-square")

        training = Training.objects.create(date=YESTERDAY)
        report = Report.objects.create(training=training, cash_at_start=1337)
        Run(
            signup=self.guest_signup,
            report=report,
            kind=Run.Kind.Flight,
            created_on=timezone.now() - timedelta(minutes=20),
        ).save()
        with self.assertNumQueries(11):
            response = self.client.get(
                reverse("update_report", kwargs={"date": YESTERDAY})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertNotContains(response, reverse("update_run", kwargs={"run": 1}))
        self.assertNotContains(response, "bi bi-pencil-square")

    def test_create_expense_button_always_shown(self):
        with self.assertNumQueries(19):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(response, reverse("create_expense", kwargs={"date": TODAY}))
        self.assertNotContains(
            response, reverse("create_expense", kwargs={"date": YESTERDAY})
        )

        training = Training.objects.create(date=YESTERDAY)
        Report(training=training, cash_at_start=1337).save()
        with self.assertNumQueries(11):
            response = self.client.get(
                reverse("update_report", kwargs={"date": YESTERDAY})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(
            response, reverse("create_expense", kwargs={"date": YESTERDAY})
        )
        self.assertNotContains(
            response, reverse("create_expense", kwargs={"date": TODAY})
        )

    def test_pilots_listed_alphabetically(self):
        with self.assertNumQueries(19):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        response_after_guest = str(response.content).split("Guest")[-1]
        self.assertTrue("Orga" in response_after_guest)

    def test_list_of_runs_with_signup_not_in_every_run(self):
        Run(
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.Flight,
            created_on=timezone.now() - timedelta(minutes=10),
        ).save()
        Run(
            signup=self.orga_signup,
            report=self.report,
            kind=Run.Kind.Flight,
            created_on=timezone.now(),
        ).save()

        with self.assertNumQueries(21):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        guest_column = (
            response.content.decode(response.charset)
            .split("Guest")[1]
            .split("</tr>")[0]
            .replace(" ", "")
            .replace("\n", "")
        )
        self.assertTrue(guest_column.endswith("<td>🪂</td><td>❌</td>"))
        orga_column = (
            response.content.decode(response.charset)
            .split("Orga")[1]
            .split("</tr>")[0]
            .replace(" ", "")
            .replace("\n", "")
        )
        self.assertTrue(orga_column.endswith("<td>❌</td><td>🪂</td>"))

    def test_no_existing_report_404(self):
        with self.assertNumQueries(4):
            response = self.client.get(
                reverse("update_report", kwargs={"date": YESTERDAY})
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")
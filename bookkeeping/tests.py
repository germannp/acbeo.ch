from datetime import date, datetime, timedelta
from http import HTTPStatus
import locale

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Report, Run
from trainings.models import Signup, Training

locale.setlocale(locale.LC_TIME, "de_CH")

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


class ReportListViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            email="orga@example.com", role=get_user_model().Role.Orga
        )
        self.client.force_login(self.orga)

        training = Training.objects.create(date=TODAY)
        self.report = Report.objects.create(training=training, cash_at_start=1337)

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
        with self.assertNumQueries(6):
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

        with self.assertNumQueries(6):
            response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/list_reports.html")
        self.assertContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 1})
        )
        self.assertNotContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 2})
        )

        with self.assertNumQueries(5):
            response = self.client.get(
                reverse("reports", kwargs={"year": TODAY.year - 1})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/list_reports.html")
        self.assertContains(response, reverse("reports", kwargs={"year": TODAY.year}))
        self.assertContains(
            response, reverse("reports", kwargs={"year": TODAY.year - 2})
        )

        with self.assertNumQueries(5):
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

        with self.assertNumQueries(6):
            response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/list_reports.html")
        self.assertContains(response, difference_between_reports)

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
        with self.assertNumQueries(6):
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
        with self.assertNumQueries(15):
            response = self.client.post(
                reverse("create_report"), data={"cash_at_start": 1337}, follow=True
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertEqual(1, len(Report.objects.all()))

    def test_redirect_to_existing_report(self):
        training = Training.objects.create(date=TODAY)
        report = Report.objects.create(training=training, cash_at_start=1337)
        with self.assertNumQueries(13):
            response = self.client.get(reverse("create_report"), follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")

        with self.assertNumQueries(13):
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
        self.guest = get_user_model().objects.create(
            first_name="Guest", email="guest@example.com"
        )
        self.orga = get_user_model().objects.create(
            first_name="Orga", email="orga@example.com", role=get_user_model().Role.Orga
        )
        self.client.force_login(self.orga)

        training = Training.objects.create(date=TODAY)
        now = datetime.now()
        Signup(pilot=self.orga, training=training, signed_up_on=now).save()
        now += timedelta(hours=1)
        Signup(pilot=self.guest, training=training, signed_up_on=now).save()

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

        with self.assertNumQueries(15):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)

        for signup in Signup.objects.all():
            self.assertEqual(signup.status, Signup.Status.Selected)

    def test_form_is_prefilled(self):
        with self.assertNumQueries(15):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(response, self.report.cash_at_start)

    def test_only_positive_integers_allowed_for_cash(self):
        with self.assertNumQueries(15):
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
        with self.assertNumQueries(15):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(response, reverse("create_run"))
        self.assertContains(response, "bi bi-plus-square")

        training = Training.objects.create(date=YESTERDAY)
        self.report = Report.objects.create(training=training, cash_at_start=1337)
        with self.assertNumQueries(9):
            response = self.client.get(
                reverse("update_report", kwargs={"date": YESTERDAY})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertNotContains(response, reverse("create_run"))
        self.assertNotContains(response, "bi bi-plus-square")

    def test_pilots_listed_alphabetically(self):
        with self.assertNumQueries(15):
            response = self.client.get(reverse("update_report", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        response_after_guest = str(response.content).split("Guest")[-1]
        self.assertTrue("Orga" in response_after_guest)

    def test_list_of_runs_with_signup_not_in_every_run(self):
        Run(
            pilot=self.guest,
            report=self.report,
            kind=Run.Kind.Flight,
            created_on=timezone.now() - timedelta(minutes=10),
        ).save()
        Run(
            pilot=self.orga,
            report=self.report,
            kind=Run.Kind.Flight,
            created_on=timezone.now(),
        ).save()

        with self.assertNumQueries(17):
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


class TestRunCreateView(TestCase):
    def setUp(self):
        self.guest = get_user_model().objects.create(
            first_name="Guest", email="guest@example.com"
        )
        guest_2 = get_user_model().objects.create(
            first_name="Guest 2", email="guest_2@example.com"
        )
        self.orga = get_user_model().objects.create(
            first_name="Orga", email="orga@example.com", role=get_user_model().Role.Orga
        )
        self.client.force_login(self.orga)

        training = Training.objects.create(date=TODAY)
        now = datetime.now()
        Signup(pilot=self.orga, training=training, signed_up_on=now).save()
        now += timedelta(hours=1)
        Signup(pilot=self.guest, training=training, signed_up_on=now).save()
        now += timedelta(hours=1)
        Signup(pilot=guest_2, training=training, signed_up_on=now).save()

        self.report = Report.objects.create(training=training, cash_at_start=1337)

    def test_orga_required_to_see(self):
        self.client.force_login(self.guest)
        with self.assertNumQueries(2):
            response = self.client.get(reverse("create_run"))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_redirect_to_create_report_if_no_report_exists(self):
        Report.objects.all().delete()
        with self.assertNumQueries(9):
            response = self.client.get(reverse("create_run"), follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_report.html")

    def test_get_create_run_selects_signups(self):
        for signup in Signup.objects.all():
            self.assertEqual(signup.status, Signup.Status.Waiting)

        with self.assertNumQueries(17):
            response = self.client.get(reverse("create_run"))
        self.assertEqual(response.status_code, HTTPStatus.OK)

        for signup in Signup.objects.all():
            self.assertEqual(signup.status, Signup.Status.Selected)

    def test_only_one_bus_per_run_allowed(self):
        with self.assertNumQueries(15):
            response = self.client.post(
                reverse("create_run"),
                data={
                    "form-TOTAL_FORMS": 3,
                    "form-INITIAL_FORMS": 0,
                    "form-0-kind": Run.Kind.Bus,
                    "form-1-kind": Run.Kind.Bus,
                    "form-2-kind": Run.Kind.Flight,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_run.html")
        self.assertContains(response, "Höchstens eine Person kann Bus fahren.")
        self.assertContains(response, f'value="{Run.Kind.Flight}" checked')
        self.assertContains(response, f'value="{Run.Kind.Bus}" checked')
        self.assertNotContains(response, f'value="{Run.Kind.Boat}" checked')
        self.assertNotContains(response, f'value="{Run.Kind.Break}" checked')
        self.assertEqual(0, len(Run.objects.all()))

    def test_at_most_two_boats_per_run_allowed(self):
        with self.assertNumQueries(15):
            response = self.client.post(
                reverse("create_run"),
                data={
                    "form-TOTAL_FORMS": 3,
                    "form-INITIAL_FORMS": 0,
                    "form-0-kind": Run.Kind.Boat,
                    "form-1-kind": Run.Kind.Boat,
                    "form-2-kind": Run.Kind.Boat,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_run.html")
        self.assertContains(response, "Höchstens zwei Personen können Boot machen.")
        self.assertContains(response, f'value="{Run.Kind.Boat}" checked')
        self.assertNotContains(response, f'value="{Run.Kind.Flight}" checked')
        self.assertNotContains(response, f'value="{Run.Kind.Bus}" checked')
        self.assertNotContains(response, f'value="{Run.Kind.Break}" checked')
        self.assertEqual(0, len(Run.objects.all()))

    def test_number_of_selected_pilots_changed(self):
        with self.assertNumQueries(26):
            response = self.client.post(
                reverse("create_run"),
                data={
                    "form-TOTAL_FORMS": 2,
                    "form-INITIAL_FORMS": 0,
                    "form-0-kind": Run.Kind.Flight,
                    "form-1-kind": Run.Kind.Flight,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_run.html")
        self.assertContains(
            response, "Die Anzahl der Teilnehmenden hat sich verändert."
        )
        self.assertEqual(0, len(Run.objects.all()))

    def test_create_run(self):
        with self.assertNumQueries(43):
            response = self.client.post(
                reverse("create_run"),
                data={
                    "form-TOTAL_FORMS": 3,
                    "form-INITIAL_FORMS": 0,
                    "form-0-kind": Run.Kind.Bus,
                    "form-1-kind": Run.Kind.Flight,
                    "form-2-kind": Run.Kind.Boat,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(response, "Run erstellt.")
        self.assertContains(response, "🚌")
        self.assertContains(response, "🪂")
        self.assertContains(response, "🚢")
        self.assertEqual(3, len(Run.objects.all()))

    def test_recently_created_run_warning(self):
        Run(
            pilot=self.guest,
            report=self.report,
            kind=Run.Kind.Flight,
            created_on=timezone.now() - timedelta(minutes=2),
        ).save()

        with self.assertNumQueries(44):
            response = self.client.post(
                reverse("create_run"),
                data={
                    "form-TOTAL_FORMS": 3,
                    "form-INITIAL_FORMS": 0,
                    "form-0-kind": Run.Kind.Bus,
                    "form-1-kind": Run.Kind.Flight,
                    "form-2-kind": Run.Kind.Boat,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(
            response,
            "Run erstellt, aber Achtung, es wurde vor weniger als fünf Minuten bereits ein Run erstellt!",
        )
        self.assertEqual(4, len(Run.objects.all()))

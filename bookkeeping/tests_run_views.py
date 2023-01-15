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


class RunCreateViewTests(TestCase):
    def setUp(self):
        orga = get_user_model().objects.create(
            first_name="Orga", email="orga@example.com", role=get_user_model().Role.Orga
        )
        self.client.force_login(orga)
        self.guest = get_user_model().objects.create(
            first_name="Guest", email="guest@example.com"
        )
        self.guest_2 = get_user_model().objects.create(
            first_name="Guest 2", email="guest_2@example.com"
        )

        training = Training.objects.create(date=TODAY)
        now = timezone.now()
        Signup(pilot=orga, training=training, signed_up_on=now).save()
        now += timedelta(hours=1)
        self.guest_signup = Signup.objects.create(
            pilot=self.guest, training=training, signed_up_on=now
        )
        now += timedelta(hours=1)
        self.guest_2_signup = Signup.objects.create(
            pilot=self.guest_2, training=training, signed_up_on=now
        )

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

        with self.assertNumQueries(20):
            response = self.client.get(reverse("create_run"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_run.html")

        for signup in Signup.objects.all():
            self.assertEqual(signup.status, Signup.Status.Selected)

    def test_forms_are_prefilled(self):
        with self.assertNumQueries(20):
            response = self.client.get(reverse("create_run"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_run.html")
        self.assertContains(response, f'value="{Run.Kind.Flight}" checked')
        self.assertNotContains(response, f'value="{Run.Kind.Flight}" \\n')

    def test_pilots_listed_alphabetically(self):
        with self.assertNumQueries(20):
            response = self.client.get(reverse("create_run"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_run.html")
        response_before_guest_2, response_after_guest_2 = str(response.content).split(
            "Guest 2"
        )
        self.assertTrue("Guest" in response_before_guest_2)
        self.assertTrue("Orga" in response_after_guest_2)

    def test_pilot_who_payed_is_hidden(self):
        Bill(signup=self.guest_2_signup, report=self.report, payed=420).save()
        self.assertTrue(self.guest_2_signup.is_payed)

        with self.assertNumQueries(19):
            response = self.client.get(reverse("create_run"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_run.html")
        self.assertNotContains(response, self.guest_2)

    def test_cannot_create_run_for_pilot_who_payed(self):
        Bill(signup=self.guest_2_signup, report=self.report, payed=420).save()
        self.assertTrue(self.guest_2_signup.is_payed)

        with self.assertNumQueries(28):
            response = self.client.post(
                reverse("create_run"),
                data={
                    "form-TOTAL_FORMS": 3,
                    "form-INITIAL_FORMS": 0,
                    "form-0-kind": Run.Kind.Bus,
                    "form-1-kind": Run.Kind.Boat,
                    "form-2-kind": Run.Kind.Flight,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/create_run.html")
        self.assertContains(
            response, "Die Anzahl der Teilnehmenden hat sich verändert."
        )
        self.assertNotContains(response, self.guest_2)
        self.assertEqual(0, len(Run.objects.all()))

    def test_only_one_bus_per_run_allowed(self):
        with self.assertNumQueries(18):
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
        with self.assertNumQueries(18):
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

    def test_number_of_selected_signups_changed(self):
        with self.assertNumQueries(29):
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
        with self.assertNumQueries(47):
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
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.Flight,
            created_on=timezone.now() - timedelta(minutes=2),
        ).save()

        with self.assertNumQueries(48):
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


class RunUpdateViewTests(TestCase):
    def setUp(self):
        orga = get_user_model().objects.create(
            first_name="Orga", email="orga@example.com", role=get_user_model().Role.Orga
        )
        self.client.force_login(orga)
        self.guest = get_user_model().objects.create(
            first_name="Guest", email="guest@example.com"
        )
        guest_2 = get_user_model().objects.create(
            first_name="Guest 2", email="guest_2@example.com"
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
        now += timedelta(hours=1)
        self.guest_2_signup = Signup.objects.create(
            pilot=guest_2, training=training, signed_up_on=now
        )

        self.report = Report.objects.create(training=training, cash_at_start=1337)
        now += timedelta(hours=5)
        self.orga_run = Run.objects.create(
            signup=self.orga_signup,
            report=self.report,
            kind=Run.Kind.Flight,
            created_on=now,
        )
        self.guest_run = Run.objects.create(
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.Flight,
            created_on=now,
        )
        self.guest_2_run = Run.objects.create(
            signup=self.guest_2_signup,
            report=self.report,
            kind=Run.Kind.Flight,
            created_on=now,
        )

    def test_orga_required_to_see(self):
        self.client.force_login(self.guest)
        with self.assertNumQueries(2):
            response = self.client.get(reverse("update_run", kwargs={"run": 1}))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_run_not_found(self):
        with self.assertNumQueries(6):
            response = self.client.get(reverse("update_run", kwargs={"run": 2}))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

    def test_forms_are_prefilled(self):
        with self.assertNumQueries(13):
            response = self.client.get(reverse("update_run", kwargs={"run": 1}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_run.html")
        self.assertContains(response, f'value="{Run.Kind.Flight}" checked')
        self.assertNotContains(response, f'value="{Run.Kind.Flight}" \n')
        self.assertContains(response, f'value="{Run.Kind.Boat}" \n')

    def test_pilots_listed_alphabetically(self):
        with self.assertNumQueries(13):
            response = self.client.get(reverse("update_run", kwargs={"run": 1}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_run.html")
        response_before_guest_2, response_after_guest_2 = str(response.content).split(
            "Guest 2"
        )
        self.assertTrue("Guest" in response_before_guest_2)
        self.assertTrue("Orga" in response_after_guest_2)

    def test_payed_run_cannot_be_updated(self):
        Bill(signup=self.guest_signup, report=self.report, payed=420).save()
        self.assertTrue(self.guest_signup.is_payed)

        with self.assertNumQueries(23):
            response = self.client.post(
                reverse("update_run", kwargs={"run": 1}),
                data={
                    "form-TOTAL_FORMS": 3,
                    "form-INITIAL_FORMS": 0,
                    "form-0-kind": Run.Kind.Bus,
                    "form-1-kind": Run.Kind.Boat,
                    "form-2-kind": Run.Kind.Break,
                    "form-0-id": self.guest_run.pk,
                    "form-1-id": self.guest_2_run.pk,
                    "form-2-id": self.orga_run.pk,
                    "save": "",
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_run.html")
        self.assertContains(response, f"{self.guest} hat bereits bezahlt.")

    def test_update_run(self):
        with self.assertNumQueries(47):
            response = self.client.post(
                reverse("update_run", kwargs={"run": 1}),
                data={
                    "form-TOTAL_FORMS": 3,
                    "form-INITIAL_FORMS": 0,
                    "form-0-kind": Run.Kind.Bus,
                    "form-1-kind": Run.Kind.Boat,
                    "form-2-kind": Run.Kind.Break,
                    "form-0-id": self.guest_run.pk,
                    "form-1-id": self.guest_2_run.pk,
                    "form-2-id": self.orga_run.pk,
                    "save": "",
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(response, "Run bearbeitet.")

        self.assertEqual(3, len(Run.objects.all()))
        self.guest_run.refresh_from_db()
        self.assertEqual(Run.Kind.Bus, self.guest_run.kind)
        self.guest_2_run.refresh_from_db()
        self.assertEqual(Run.Kind.Boat, self.guest_2_run.kind)
        self.orga_run.refresh_from_db()
        self.assertEqual(Run.Kind.Break, self.orga_run.kind)

    def test_run_with_changed_number_of_pilots_cannot_be_deleted(self):
        with self.assertNumQueries(41):
            response = self.client.post(
                reverse("update_run", kwargs={"run": 1}),
                data={
                    "form-TOTAL_FORMS": 2,
                    "form-INITIAL_FORMS": 0,
                    "form-0-kind": Run.Kind.Bus,
                    "form-1-kind": Run.Kind.Flight,
                    "delete": "",
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(
            response, "Run hat sich verändert und wurde nicht gelöscht!"
        )
        self.assertEqual(3, len(Run.objects.all()))

    def test_run_with_changed_kind_cannot_be_deleted(self):
        with self.assertNumQueries(41):
            response = self.client.post(
                reverse("update_run", kwargs={"run": 1}),
                data={
                    "form-TOTAL_FORMS": 3,
                    "form-INITIAL_FORMS": 0,
                    "form-0-kind": Run.Kind.Bus,
                    "form-1-kind": Run.Kind.Flight,
                    "form-2-kind": Run.Kind.Flight,
                    "delete": "",
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(
            response, "Run hat sich verändert und wurde nicht gelöscht!"
        )
        self.assertEqual(3, len(Run.objects.all()))

    def test_payed_run_cannot_be_deleted(self):
        Bill(signup=self.guest_signup, report=self.report, payed=420).save()
        self.assertTrue(self.guest_signup.is_payed)
        self.assertEqual(3, len(Run.objects.all()))

        with self.assertNumQueries(38):
            response = self.client.post(
                reverse("update_run", kwargs={"run": 1}),
                data={
                    "form-TOTAL_FORMS": 3,
                    "form-INITIAL_FORMS": 0,
                    "form-0-kind": Run.Kind.Flight,
                    "form-1-kind": Run.Kind.Flight,
                    "form-2-kind": Run.Kind.Flight,
                    "delete": "",
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(
            response, f"{self.guest} hat bereits bezahlt, Run wurde nicht gelöscht!"
        )
        self.assertEqual(3, len(Run.objects.all()))

    def test_delete_run(self):
        with self.assertNumQueries(39):
            response = self.client.post(
                reverse("update_run", kwargs={"run": 1}),
                data={
                    "form-TOTAL_FORMS": 3,
                    "form-INITIAL_FORMS": 0,
                    "form-0-kind": Run.Kind.Flight,
                    "form-1-kind": Run.Kind.Flight,
                    "form-2-kind": Run.Kind.Flight,
                    "delete": "",
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/update_report.html")
        self.assertContains(response, "Run gelöscht.")
        self.assertEqual(0, len(Run.objects.all()))

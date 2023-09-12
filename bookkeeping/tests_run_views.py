from datetime import timedelta
from http import HTTPStatus
from random import randint

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Bill, PaymentMethods, Report, Run
from trainings.models import Signup, Training


TODAY = timezone.now().date()
YESTERDAY = TODAY - timedelta(days=1)


class RunCreateViewTests(TestCase):
    def setUp(self):
        orga = get_user_model().objects.create(
            first_name="Orga", email="orga@example.com", role=get_user_model().Role.ORGA
        )
        self.client.force_login(orga)
        self.guest = get_user_model().objects.create(
            first_name="Guest", email="guest@example.com"
        )
        self.guest_2 = get_user_model().objects.create(
            first_name="Guest 2", email="guest_2@example.com"
        )

        training = Training.objects.create(date=TODAY, emergency_mail_sender=orga)
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
        response = self.client.get(reverse("create_run"))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_redirect_to_create_report_if_no_report_exists(self):
        Report.objects.all().delete()
        response = self.client.get(reverse("create_run"), follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_create.html")

    def test_get_create_run_selects_signups(self):
        for signup in Signup.objects.all():
            self.assertEqual(signup.status, Signup.Status.WAITING)

        response = self.client.get(reverse("create_run"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/run_create.html")

        for signup in Signup.objects.all():
            self.assertEqual(signup.status, Signup.Status.SELECTED)

    def test_forms_are_prefilled(self):
        response = self.client.get(reverse("create_run"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/run_create.html")
        self.assertContains(response, f'value="{Run.Kind.FLIGHT}" checked')
        self.assertNotContains(response, f'value="{Run.Kind.FLIGHT}" \\n')

    def test_pilots_listed_alphabetically(self):
        response = self.client.get(reverse("create_run"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/run_create.html")
        response_before_guest_2, response_after_guest_2 = str(response.content).split(
            "Guest 2"
        )
        self.assertTrue("Guest" in response_before_guest_2)
        self.assertTrue("Orga" in response_after_guest_2)

    def test_pilot_who_paid_is_hidden(self):
        Bill(
            signup=self.guest_2_signup,
            report=self.report,
            prepaid_flights=0,
            amount=420,
            method=PaymentMethods.CASH,
        ).save()
        self.assertTrue(self.guest_2_signup.is_paid)

        response = self.client.get(reverse("create_run"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/run_create.html")
        self.assertNotContains(response, self.guest_2)

    def test_cannot_create_run_for_pilot_who_paid(self):
        Bill(
            signup=self.guest_2_signup,
            report=self.report,
            prepaid_flights=0,
            amount=420,
            method=PaymentMethods.CASH,
        ).save()
        self.assertTrue(self.guest_2_signup.is_paid)

        response = self.client.post(
            reverse("create_run"),
            data={
                "form-TOTAL_FORMS": 3,
                "form-INITIAL_FORMS": 0,
                "form-0-kind": Run.Kind.BUS,
                "form-1-kind": Run.Kind.BOAT,
                "form-2-kind": Run.Kind.FLIGHT,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/run_create.html")
        self.assertContains(
            response, "Die Anzahl der Teilnehmenden hat sich verändert."
        )
        self.assertNotContains(response, self.guest_2)
        self.assertEqual(0, len(Run.objects.all()))

    def test_only_one_bus_per_run_allowed(self):
        response = self.client.post(
            reverse("create_run"),
            data={
                "form-TOTAL_FORMS": 3,
                "form-INITIAL_FORMS": 0,
                "form-0-kind": Run.Kind.BUS,
                "form-1-kind": Run.Kind.BUS,
                "form-2-kind": Run.Kind.FLIGHT,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/run_create.html")
        self.assertContains(response, "Höchstens eine Person kann Bus fahren.")
        self.assertContains(response, f'value="{Run.Kind.FLIGHT}" checked')
        self.assertContains(response, f'value="{Run.Kind.BUS}" checked')
        self.assertNotContains(response, f'value="{Run.Kind.BOAT}" checked')
        self.assertNotContains(response, f'value="{Run.Kind.BREAK}" checked')
        self.assertEqual(0, len(Run.objects.all()))

    def test_at_most_two_boats_per_run_allowed(self):
        response = self.client.post(
            reverse("create_run"),
            data={
                "form-TOTAL_FORMS": 3,
                "form-INITIAL_FORMS": 0,
                "form-0-kind": Run.Kind.BOAT,
                "form-1-kind": Run.Kind.BOAT,
                "form-2-kind": Run.Kind.BOAT,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/run_create.html")
        self.assertContains(response, "Höchstens zwei Personen können Boot machen.")
        self.assertContains(response, f'value="{Run.Kind.BOAT}" checked')
        self.assertNotContains(response, f'value="{Run.Kind.FLIGHT}" checked')
        self.assertNotContains(response, f'value="{Run.Kind.BUS}" checked')
        self.assertNotContains(response, f'value="{Run.Kind.BREAK}" checked')
        self.assertEqual(0, len(Run.objects.all()))

    def test_number_of_selected_signups_changed(self):
        response = self.client.post(
            reverse("create_run"),
            data={
                "form-TOTAL_FORMS": 2,
                "form-INITIAL_FORMS": 0,
                "form-0-kind": Run.Kind.FLIGHT,
                "form-1-kind": Run.Kind.FLIGHT,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/run_create.html")
        self.assertContains(
            response, "Die Anzahl der Teilnehmenden hat sich verändert."
        )
        self.assertEqual(0, len(Run.objects.all()))

    def test_create_run(self):
        response = self.client.post(
            reverse("create_run"),
            data={
                "form-TOTAL_FORMS": 3,
                "form-INITIAL_FORMS": 0,
                "form-0-kind": Run.Kind.BUS,
                "form-1-kind": Run.Kind.FLIGHT,
                "form-2-kind": Run.Kind.BOAT,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, "Run erstellt.")
        self.assertContains(response, "🚌")
        self.assertContains(response, "🪂")
        self.assertContains(response, "🚢")
        self.assertEqual(3, len(Run.objects.all()))

    def test_recently_created_run_warning(self):
        Run(
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.FLIGHT,
            created_on=timezone.now() - timedelta(minutes=20),
        ).save()

        response = self.client.post(
            reverse("create_run"),
            data={
                "form-TOTAL_FORMS": 3,
                "form-INITIAL_FORMS": 0,
                "form-0-kind": Run.Kind.BUS,
                "form-1-kind": Run.Kind.FLIGHT,
                "form-2-kind": Run.Kind.BOAT,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(
            response,
            "Run erstellt, aber Achtung, es wurde vor weniger als einer halben Stunde bereits ein Run erstellt!",
        )
        self.assertEqual(4, len(Run.objects.all()))


class RunUpdateViewTests(TestCase):
    def setUp(self):
        orga = get_user_model().objects.create(
            first_name="Orga", email="orga@example.com", role=get_user_model().Role.ORGA
        )
        self.client.force_login(orga)
        self.guest = get_user_model().objects.create(
            first_name="Guest", email="guest@example.com"
        )
        guest_2 = get_user_model().objects.create(
            first_name="Guest 2", email="guest_2@example.com"
        )

        training = Training.objects.create(date=TODAY, emergency_mail_sender=orga)
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
            kind=Run.Kind.FLIGHT,
            created_on=now,
        )
        self.guest_run = Run.objects.create(
            signup=self.guest_signup,
            report=self.report,
            kind=Run.Kind.FLIGHT,
            created_on=now,
        )
        self.guest_2_run = Run.objects.create(
            signup=self.guest_2_signup,
            report=self.report,
            kind=Run.Kind.FLIGHT,
            created_on=now,
        )

    def test_orga_required_to_see(self):
        self.client.force_login(self.guest)
        response = self.client.get(reverse("update_run", kwargs={"run": 1}))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_run_not_found(self):
        response = self.client.get(reverse("update_run", kwargs={"run": 2}))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

    def test_forms_are_prefilled(self):
        response = self.client.get(reverse("update_run", kwargs={"run": 1}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/run_update.html")
        self.assertContains(response, f'value="{Run.Kind.FLIGHT}" checked')
        self.assertNotContains(response, f'value="{Run.Kind.FLIGHT}" \n')
        self.assertContains(response, f'value="{Run.Kind.BOAT}" \n')

    def test_pilots_listed_alphabetically(self):
        response = self.client.get(reverse("update_run", kwargs={"run": 1}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/run_update.html")
        response_before_guest_2, response_after_guest_2 = str(response.content).split(
            "Guest 2"
        )
        self.assertTrue("Guest" in response_before_guest_2)
        self.assertTrue("Orga" in response_after_guest_2)

    def test_paid_run_cannot_be_updated(self):
        Bill(
            signup=self.guest_signup,
            report=self.report,
            prepaid_flights=0,
            amount=420,
            method=PaymentMethods.CASH,
        ).save()
        self.assertTrue(self.guest_signup.is_paid)

        response = self.client.post(
            reverse("update_run", kwargs={"run": 1}),
            data={
                "form-TOTAL_FORMS": 3,
                "form-INITIAL_FORMS": 0,
                "form-0-kind": Run.Kind.BUS,
                "form-1-kind": Run.Kind.BOAT,
                "form-2-kind": Run.Kind.BREAK,
                "form-0-id": self.guest_run.pk,
                "form-1-id": self.guest_2_run.pk,
                "form-2-id": self.orga_run.pk,
                "save": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/run_update.html")
        self.assertContains(response, f"{self.guest} hat bereits bezahlt.")

    def test_update_run(self):
        response = self.client.post(
            reverse("update_run", kwargs={"run": 1}),
            data={
                "form-TOTAL_FORMS": 3,
                "form-INITIAL_FORMS": 0,
                "form-0-kind": Run.Kind.BUS,
                "form-1-kind": Run.Kind.BOAT,
                "form-2-kind": Run.Kind.BREAK,
                "form-0-id": self.guest_run.pk,
                "form-1-id": self.guest_2_run.pk,
                "form-2-id": self.orga_run.pk,
                "save": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, "Run bearbeitet.")

        self.assertEqual(3, len(Run.objects.all()))
        self.guest_run.refresh_from_db()
        self.assertEqual(Run.Kind.BUS, self.guest_run.kind)
        self.guest_2_run.refresh_from_db()
        self.assertEqual(Run.Kind.BOAT, self.guest_2_run.kind)
        self.orga_run.refresh_from_db()
        self.assertEqual(Run.Kind.BREAK, self.orga_run.kind)

    def test_run_with_changed_number_of_pilots_cannot_be_deleted(self):
        response = self.client.post(
            reverse("update_run", kwargs={"run": 1}),
            data={
                "form-TOTAL_FORMS": 2,
                "form-INITIAL_FORMS": 0,
                "form-0-kind": Run.Kind.BUS,
                "form-1-kind": Run.Kind.FLIGHT,
                "delete": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(
            response, "Run hat sich verändert und wurde nicht gelöscht!"
        )
        self.assertEqual(3, len(Run.objects.all()))

    def test_run_with_changed_kind_cannot_be_deleted(self):
        response = self.client.post(
            reverse("update_run", kwargs={"run": 1}),
            data={
                "form-TOTAL_FORMS": 3,
                "form-INITIAL_FORMS": 0,
                "form-0-kind": Run.Kind.BUS,
                "form-1-kind": Run.Kind.FLIGHT,
                "form-2-kind": Run.Kind.FLIGHT,
                "delete": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(
            response, "Run hat sich verändert und wurde nicht gelöscht!"
        )
        self.assertEqual(3, len(Run.objects.all()))

    def test_paid_run_cannot_be_deleted(self):
        Bill(
            signup=self.guest_signup,
            report=self.report,
            prepaid_flights=0,
            amount=420,
            method=PaymentMethods.CASH,
        ).save()
        self.assertTrue(self.guest_signup.is_paid)
        self.assertEqual(3, len(Run.objects.all()))

        response = self.client.post(
            reverse("update_run", kwargs={"run": 1}),
            data={
                "form-TOTAL_FORMS": 3,
                "form-INITIAL_FORMS": 0,
                "form-0-kind": Run.Kind.FLIGHT,
                "form-1-kind": Run.Kind.FLIGHT,
                "form-2-kind": Run.Kind.FLIGHT,
                "delete": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(
            response, f"{self.guest} hat bereits bezahlt, Run wurde nicht gelöscht!"
        )
        self.assertEqual(3, len(Run.objects.all()))

    def test_delete_run(self):
        response = self.client.post(
            reverse("update_run", kwargs={"run": 1}),
            data={
                "form-TOTAL_FORMS": 3,
                "form-INITIAL_FORMS": 0,
                "form-0-kind": Run.Kind.FLIGHT,
                "form-1-kind": Run.Kind.FLIGHT,
                "form-2-kind": Run.Kind.FLIGHT,
                "delete": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/report_update.html")
        self.assertContains(response, "Run gelöscht.")
        self.assertEqual(0, len(Run.objects.all()))


class DatabaseCallsTests(TestCase):
    def setUp(self):
        self.num_pilots = randint(5, 10)
        num_flights = randint(5, 10)

        orga = get_user_model().objects.create(
            email="orga@example.com", first_name="Orga", role=get_user_model().Role.ORGA
        )
        self.client.force_login(orga)

        pilots = [orga] + [
            get_user_model().objects.create(
                email=f"pilot_{i}@example.com", first_name=f"Pilot {i}"
            )
            for i in range(self.num_pilots - 1)
        ]
        training = Training.objects.create(date=TODAY)
        report = Report.objects.create(training=training, cash_at_start=420)
        now = timezone.now()
        self.runs = []
        for pilot in pilots:
            signup = Signup.objects.create(pilot=pilot, training=training)
            for j in range(num_flights):
                created_on = now + timedelta(minutes=j)
                self.runs.append(Run.objects.create(
                    signup=signup,
                    report=report,
                    kind=Run.Kind.FLIGHT,
                    created_on=created_on,
                ))
        training.select_signups()

    def test_run_create_view(self):
        with self.assertNumQueries(13):
            response = self.client.get(reverse("create_run"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/run_create.html")

        data = {"form-TOTAL_FORMS": self.num_pilots, "form-INITIAL_FORMS": 0}
        for i in range(self.num_pilots):
            data[f"form-{i}-kind"] = Run.Kind.FLIGHT
        # Creating each run costs a call 🤷
        with self.assertNumQueries(11 + self.num_pilots):
            response = self.client.post(reverse("create_run"), data=data)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

    def test_run_update_view(self):
        with self.assertNumQueries(11):
            response = self.client.get(reverse("update_run", kwargs={"run": 1}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "bookkeeping/run_update.html")

        data = {"form-TOTAL_FORMS": self.num_pilots, "form-INITIAL_FORMS": 0, "save": ""}
        for i in range(self.num_pilots):
            data[f"form-{i}-kind"] = Run.Kind.FLIGHT
            data[f"form-{i}-id"] = self.runs[i].pk
        # Unfortunately, validating a formset costs a call for each form and caching
        # would be complicated, see https://stackoverflow.com/questions/40665770/.
        with self.assertNumQueries(9 + 2 * self.num_pilots):
            response = self.client.post(
                reverse("update_run", kwargs={"run": 1}), data=data, follow=False
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

        del data["save"]
        data["delete"] = ""
        # Deleting can be done in one go, validation still costs.
        with self.assertNumQueries(10 + self.num_pilots):
            response = self.client.post(
                reverse("update_run", kwargs={"run": 1}), data=data, follow=False
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

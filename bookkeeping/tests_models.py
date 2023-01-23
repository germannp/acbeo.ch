from datetime import date, timedelta
from itertools import product

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .models import Bill, Expense, Report, Run
from trainings.models import Signup, Training


TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


class ReportTests(TestCase):
    def setUp(self):
        orga = get_user_model().objects.create(
            first_name="Orga", email="orga@example.com"
        )
        pilot = get_user_model().objects.create(
            first_name="Pilot", email="pilot@example.com"
        )
        training = Training.objects.create(date=TODAY)
        self.orga_signup = Signup.objects.create(pilot=orga, training=training)
        self.pilot_signup = Signup.objects.create(pilot=pilot, training=training)
        self.report = Report.objects.create(
            training=training, cash_at_start=1337, cash_at_end=2337
        )

    def test_details(self):
        self.assertEqual(self.report.details["difference"], 1000)
        self.assertEqual(self.report.details["revenue"], 0)
        self.assertEqual(self.report.details["expenses"], 0)

        Bill(signup=self.orga_signup, report=self.report, payed=700).save()
        self.assertEqual(self.report.details["difference"], 300)
        self.assertEqual(self.report.details["revenue"], 700)
        self.assertEqual(self.report.details["expenses"], 0)

        Bill(signup=self.pilot_signup, report=self.report, payed=300).save()
        self.assertEqual(self.report.details["difference"], 0)
        self.assertEqual(self.report.details["revenue"], 1000)
        self.assertEqual(self.report.details["expenses"], 0)

        Expense(report=self.report, reason="Gas", amount=100).save()
        self.assertEqual(self.report.details["difference"], 100)
        self.assertEqual(self.report.details["revenue"], 1000)
        self.assertEqual(self.report.details["expenses"], 100)

        Expense(report=self.report, reason="Parking", amount=200).save()
        self.assertEqual(self.report.details["difference"], 300)
        self.assertEqual(self.report.details["revenue"], 1000)
        self.assertEqual(self.report.details["expenses"], 300)


class RunTests(SimpleTestCase):
    def setUp(self):
        pilot = get_user_model()(first_name="Pilot", email="pilot@example.com")
        training = Training(date=TODAY)
        self.signup = Signup(pilot=pilot, training=training)
        self.report = Report(training=training, cash_at_start=1337)

    def test_is_relevant_for_bill(self):
        for kind, is_relevant_for_bill in [
            (Run.Kind.Flight, True),
            (Run.Kind.Bus, True),
            (Run.Kind.Boat, True),
            (Run.Kind.Break, False),
        ]:
            with self.subTest(kind=kind, is_relevant_for_bill=is_relevant_for_bill):
                run = Run(
                    signup=self.signup,
                    report=self.report,
                    kind=kind,
                    created_on=timezone.now(),
                )
                self.assertEqual(run.is_relevant_for_bill, is_relevant_for_bill)

    def test_is_flight(self):
        for kind, is_flight in [
            (Run.Kind.Flight, True),
            (Run.Kind.Bus, False),
            (Run.Kind.Boat, False),
            (Run.Kind.Break, False),
        ]:
            with self.subTest(kind=kind, is_flight=is_flight):
                run = Run(
                    signup=self.signup,
                    report=self.report,
                    kind=kind,
                    created_on=timezone.now(),
                )
                self.assertEqual(run.is_flight, is_flight)

    def test_is_service(self):
        for kind, is_service in [
            (Run.Kind.Flight, False),
            (Run.Kind.Bus, True),
            (Run.Kind.Boat, True),
            (Run.Kind.Break, False),
        ]:
            with self.subTest(kind=kind, is_service=is_service):
                run = Run(
                    signup=self.signup,
                    report=self.report,
                    kind=kind,
                    created_on=timezone.now(),
                )
                self.assertEqual(run.is_service, is_service)

    def test_cannot_save_run_for_payed_signup(self):
        Bill(signup=self.signup, report=self.report)
        self.assertTrue(self.signup.is_payed)
        with self.assertRaises(ValidationError):
            Run(
                signup=self.signup,
                report=self.report,
                kind=Run.Kind.Flight,
                created_on=timezone.now(),
            ).save()


class BillTests(TestCase):
    def setUp(self):
        self.pilot = get_user_model().objects.create(
            first_name="Pilot", email="pilot@example.com"
        )
        self.training = Training.objects.create(date=TODAY)
        self.report = Report.objects.create(training=self.training, cash_at_start=1337)

    def test_details(self):
        for num_flights, num_buses, num_boats, num_breaks in product(
            range(1, 9), range(1, 3), range(1, 3), range(3)
        ):
            with self.subTest(
                num_flights=num_flights,
                num_buses=num_buses,
                num_boats=num_boats,
                num_breaks=num_breaks,
            ):
                signup = Signup.objects.create(pilot=self.pilot, training=self.training)
                now = timezone.now()
                for _ in range(num_flights):
                    now += timedelta(hours=1)
                    Run(
                        signup=signup,
                        report=self.report,
                        kind=Run.Kind.Flight,
                        created_on=now,
                    ).save()
                for _ in range(num_buses):
                    now += timedelta(hours=1)
                    Run(
                        signup=signup,
                        report=self.report,
                        kind=Run.Kind.Bus,
                        created_on=now,
                    ).save()
                for _ in range(num_boats):
                    now += timedelta(hours=1)
                    Run(
                        signup=signup,
                        report=self.report,
                        kind=Run.Kind.Boat,
                        created_on=now,
                    ).save()
                for _ in range(num_breaks):
                    now += timedelta(hours=1)
                    Run(
                        signup=signup,
                        report=self.report,
                        kind=Run.Kind.Break,
                        created_on=now,
                    ).save()

                bill = Bill(signup=signup, report=self.report)
                self.assertEqual(bill.details["num_flights"], num_flights)
                self.assertEqual(bill.details["num_services"], num_buses + num_boats)
                self.assertEqual(
                    bill.details["to_pay"],
                    (num_flights - (num_buses + num_boats)) * Bill.PRICE_OF_FLIGHT,
                )

                # Tear down sub test.
                Run.objects.all().delete()
                signup.delete()

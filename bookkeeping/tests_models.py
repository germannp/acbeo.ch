from datetime import date, timedelta
from itertools import product

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .models import Bill, Expense, Purchase, Report, Run
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
        guest = get_user_model().objects.create(
            first_name="Guest", email="guest@example.com"
        )
        training = Training.objects.create(date=TODAY)
        self.orga_signup = Signup.objects.create(pilot=orga, training=training)
        self.pilot_signup = Signup.objects.create(pilot=pilot, training=training)
        self.guest_signup = Signup.objects.create(pilot=guest, training=training)
        self.report = Report.objects.create(
            training=training, cash_at_start=1337, cash_at_end=2337
        )

    def test_bookkeeping(self):
        self.assertEqual(self.report.cash_revenue, 0)
        self.assertEqual(self.report.other_revenue, 0)
        self.assertEqual(self.report.total_expenses, 0)
        self.assertEqual(self.report.difference, 1000)

        Bill(
            signup=self.orga_signup,
            report=self.report,
            prepaid_flights=0,
            paid=700,
            method=Bill.METHODS.CASH,
        ).save()
        self.assertEqual(self.report.cash_revenue, 700)
        self.assertEqual(self.report.other_revenue, 0)
        self.assertEqual(self.report.total_expenses, 0)
        self.assertEqual(self.report.difference, 300)

        Bill(
            signup=self.pilot_signup,
            report=self.report,
            prepaid_flights=0,
            paid=300,
            method=Bill.METHODS.CASH,
        ).save()
        self.assertEqual(self.report.cash_revenue, 1000)
        self.assertEqual(self.report.other_revenue, 0)
        self.assertEqual(self.report.total_expenses, 0)
        self.assertEqual(self.report.difference, 0)

        Expense(report=self.report, reason="Gas", amount=100).save()
        self.assertEqual(self.report.cash_revenue, 1000)
        self.assertEqual(self.report.other_revenue, 0)
        self.assertEqual(self.report.total_expenses, 100)
        self.assertEqual(self.report.difference, 100)

        Expense(report=self.report, reason="Parking", amount=200).save()
        self.assertEqual(self.report.cash_revenue, 1000)
        self.assertEqual(self.report.other_revenue, 0)
        self.assertEqual(self.report.total_expenses, 300)
        self.assertEqual(self.report.difference, 300)

        Bill(
            signup=self.guest_signup,
            report=self.report,
            prepaid_flights=0,
            paid=400,
            method=Bill.METHODS.TWINT,
        ).save()
        self.assertEqual(self.report.cash_revenue, 1000)
        self.assertEqual(self.report.other_revenue, 400)
        self.assertEqual(self.report.total_expenses, 300)
        self.assertEqual(self.report.difference, 300)


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

    def test_cannot_save_run_for_paid_signup(self):
        Bill(signup=self.signup, report=self.report)
        self.assertTrue(self.signup.is_paid)
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
            first_name="Pilot", email="pilot@example.com", prepaid_flights=10
        )
        self.training = Training.objects.create(date=TODAY)
        self.report = Report.objects.create(training=self.training, cash_at_start=1337)

    def test_bookkeeping(self):
        for (
            num_flights,
            num_buses,
            num_boats,
            num_breaks,
            price_of_purchase,
            initial_prepaid_flights,
            num_flights_to_pay,
            final_prepaid_flights,
        ) in [
            (5, 1, 0, 0, 0, 7, 0, 3),  # Normal training with all flights prepaid
            (5, 1, 0, 0, 0, 2, 2, 0),  # Normal training with some flights prepaid
            (5, 1, 0, 0, 0, 0, 4, 0),  # Normal training w/o prepaid flights
            (1, 3, 1, 1, 36, 7, 0, 10),  # Rescue on the first run
        ]:
            with self.subTest(
                num_flights=num_flights,
                num_buses=num_buses,
                num_boats=num_boats,
                num_breaks=num_breaks,
                price_of_purchase=price_of_purchase,
                initial_prepaid_flights=initial_prepaid_flights,
                num_flights_to_pay=num_flights_to_pay,
                final_prepaid_flights=final_prepaid_flights,
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

                self.pilot.prepaid_flights = initial_prepaid_flights
                self.pilot.save()

                if price_of_purchase:
                    Purchase(
                        signup=signup,
                        report=self.report,
                        description="Description",
                        price=price_of_purchase,
                    ).save()

                bill = Bill(signup=signup, report=self.report, method=Bill.METHODS.CASH)
                self.assertEqual(bill.num_flights, num_flights)
                self.assertEqual(bill.num_services, num_buses + num_boats)
                self.assertEqual(
                    bill.to_pay,
                    num_flights_to_pay * Bill.PRICE_OF_FLIGHT + price_of_purchase,
                )

                bill.prepaid_flights = bill.num_prepaid_flights
                bill.paid = bill.to_pay
                bill.save()
                self.assertEqual(final_prepaid_flights, self.pilot.prepaid_flights)

                bill.delete()
                self.assertEqual(initial_prepaid_flights, self.pilot.prepaid_flights)

                # Tear down sub test.
                signup.delete()

    def test_update_does_not_affect_prepaid_flights(self):
        signup = Signup.objects.create(pilot=self.pilot, training=self.training)
        bill = Bill.objects.create(
            signup=signup,
            report=self.report,
            prepaid_flights=2,
            paid=0,
            method=Bill.METHODS.CASH,
        )
        self.assertEqual(8, self.pilot.prepaid_flights)

        bill.method = Bill.METHODS.TWINT
        bill.save()
        self.assertEqual(8, self.pilot.prepaid_flights)

    def test_was_paid_in_cash(self):
        signup = Signup.objects.create(pilot=self.pilot, training=self.training)
        for method in Bill.METHODS:
            with self.subTest(method=method):
                bill = Bill.objects.create(
                    signup=signup,
                    report=self.report,
                    prepaid_flights=0,
                    paid=420,
                    method=method,
                )
                self.assertEqual(method == Bill.METHODS.CASH, bill.was_paid_in_cash)
                bill.delete()


class PurchaseTests(TestCase):
    def setUp(self):
        self.pilot = get_user_model().objects.create(
            first_name="Pilot", email="pilot@example.com"
        )
        training = Training.objects.create(date=TODAY)
        self.signup = Signup.objects.create(pilot=self.pilot, training=training)
        self.report = Report.objects.create(training=training, cash_at_start=0)

    def test_is_day_pass(self):
        for item in Purchase.ITEMS:
            with self.subTest(item=item):
                purchase = Purchase.save_item(self.signup, self.report, item)
                self.assertFalse(purchase.is_day_pass)

        purchase = Purchase.save_day_pass(self.signup, self.report)
        self.assertTrue(purchase.is_day_pass)

    def test_is_equipment(self):
        for item in Purchase.ITEMS:
            with self.subTest(item=item):
                purchase = Purchase.save_item(self.signup, self.report, item)
                self.assertEqual(
                    item != Purchase.ITEMS.PREPAID_FLIGHTS, purchase.is_equipment
                )

        purchase = Purchase.save_day_pass(self.signup, self.report)
        self.assertFalse(purchase.is_equipment)

    def test_create_and_delete_prepaid_flights(self):
        self.assertEqual(0, self.pilot.prepaid_flights)
        Purchase.save_item(self.signup, self.report, Purchase.ITEMS.PREPAID_FLIGHTS)
        self.assertEqual(10, self.pilot.prepaid_flights)
        Purchase.objects.all().delete()
        self.pilot.refresh_from_db()
        self.assertEqual(0, self.pilot.prepaid_flights)

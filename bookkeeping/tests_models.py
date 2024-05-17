from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .models import Bill, Expense, PaymentMethods, Purchase, Report, Run
from trainings.models import Signup, Training


TODAY = timezone.now().date()
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
        self.assertEqual(self.report.cash_expediture, 0)
        self.assertEqual(self.report.difference, 1000)

        Bill(
            signup=self.orga_signup,
            report=self.report,
            prepaid_flights=0,
            amount=700,
            method=PaymentMethods.CASH,
        ).save()
        self.assertEqual(self.report.cash_revenue, 700)
        self.assertEqual(self.report.other_revenue, 0)
        self.assertEqual(self.report.cash_expediture, 0)
        self.assertEqual(self.report.difference, 300)

        Bill(
            signup=self.pilot_signup,
            report=self.report,
            prepaid_flights=0,
            amount=300,
            method=PaymentMethods.CASH,
        ).save()
        self.assertEqual(self.report.cash_revenue, 1000)
        self.assertEqual(self.report.other_revenue, 0)
        self.assertEqual(self.report.cash_expediture, 0)
        self.assertEqual(self.report.difference, 0)

        Expense(report=self.report, reason="Gas", amount=100).save()
        self.assertEqual(self.report.cash_revenue, 1000)
        self.assertEqual(self.report.other_revenue, 0)
        self.assertEqual(self.report.cash_expediture, 100)
        self.assertEqual(self.report.difference, 100)

        Expense(report=self.report, reason="Parking", amount=200).save()
        self.assertEqual(self.report.cash_revenue, 1000)
        self.assertEqual(self.report.other_revenue, 0)
        self.assertEqual(self.report.cash_expediture, 300)
        self.assertEqual(self.report.difference, 300)

        Bill(
            signup=self.guest_signup,
            report=self.report,
            prepaid_flights=0,
            amount=400,
            method=PaymentMethods.TWINT,
        ).save()
        self.assertEqual(self.report.cash_revenue, 1000)
        self.assertEqual(self.report.other_revenue, 400)
        self.assertEqual(self.report.cash_expediture, 300)
        self.assertEqual(self.report.difference, 300)


class RunTests(SimpleTestCase):
    def setUp(self):
        pilot = get_user_model()(first_name="Pilot", email="pilot@example.com")
        training = Training(date=TODAY)
        self.signup = Signup(pilot=pilot, training=training)
        self.report = Report(training=training, cash_at_start=1337)

    def test_is_relevant_for_bill(self):
        for kind, is_relevant_for_bill in [
            (Run.Kind.FLIGHT, True),
            (Run.Kind.BUS, True),
            (Run.Kind.BOAT, True),
            (Run.Kind.BREAK, False),
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
            (Run.Kind.FLIGHT, True),
            (Run.Kind.BUS, False),
            (Run.Kind.BOAT, False),
            (Run.Kind.BREAK, False),
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
            (Run.Kind.FLIGHT, False),
            (Run.Kind.BUS, True),
            (Run.Kind.BOAT, True),
            (Run.Kind.BREAK, False),
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
                kind=Run.Kind.FLIGHT,
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
        @dataclass
        class BookkeepingTestCase:
            num_flights_with_bus: int = 0
            num_flights_with_lift: int = 0
            num_flights_with_postbus: int = 0
            num_buses: int = 0
            num_boats: int = 0
            num_breaks: int = 0
            price_of_purchase: int = 0
            initial_prepaid_flights: int = 0
            num_flights_to_pay: Decimal = 0
            final_prepaid_flights: Decimal = 0

        for test in [
            # Training w/o prepaid flights
            BookkeepingTestCase(
                num_flights_with_bus=5, num_boats=1, num_flights_to_pay=4
            ),
            # Training with all flights prepaid
            BookkeepingTestCase(
                num_flights_with_bus=5,
                num_buses=1,
                initial_prepaid_flights=7,
                final_prepaid_flights=3,
            ),
            # Training with all flights prepaid using lift
            BookkeepingTestCase(
                num_flights_with_lift=5,
                initial_prepaid_flights=7,
                final_prepaid_flights=4.5,
            ),
            # Training with some flights prepaid
            BookkeepingTestCase(
                num_flights_with_bus=5,
                num_buses=1,
                initial_prepaid_flights=2,
                num_flights_to_pay=2,
                final_prepaid_flights=0,
            ),
            # Training with lift, except over lunch
            BookkeepingTestCase(
                num_flights_with_lift=5,
                num_flights_with_bus=1,
                initial_prepaid_flights=2,
                num_flights_to_pay=1.5,
                final_prepaid_flights=0,
            ),
            # Training with final run using postbus
            BookkeepingTestCase(
                num_flights_with_bus=4,
                num_flights_with_postbus=1,
                initial_prepaid_flights=2,
                num_flights_to_pay=2,
                final_prepaid_flights=0,
            ),
            # Rescue on the first run
            BookkeepingTestCase(
                num_flights_with_bus=1,
                num_boats=3,
                num_buses=1,
                num_breaks=1,
                price_of_purchase=36,
                initial_prepaid_flights=7,
                final_prepaid_flights=10,
            ),
        ]:
            with self.subTest(test=test):
                signup = Signup.objects.create(pilot=self.pilot, training=self.training)
                now = timezone.now()
                for _ in range(test.num_flights_with_bus):
                    now += timedelta(hours=1)
                    Run(
                        signup=signup,
                        report=self.report,
                        kind=Run.Kind.FLIGHT,
                        created_on=now,
                    ).save()
                for _ in range(test.num_flights_with_lift):
                    now += timedelta(hours=1)
                    Run(
                        signup=signup,
                        report=self.report,
                        kind=Run.Kind.FLIGHT_WITH_LIFT,
                        created_on=now,
                    ).save()
                for _ in range(test.num_flights_with_postbus):
                    now += timedelta(hours=1)
                    Run(
                        signup=signup,
                        report=self.report,
                        kind=Run.Kind.FLIGHT_WITH_POSTBUS,
                        created_on=now,
                    ).save()
                for _ in range(test.num_buses):
                    now += timedelta(hours=1)
                    Run(
                        signup=signup,
                        report=self.report,
                        kind=Run.Kind.BUS,
                        created_on=now,
                    ).save()
                for _ in range(test.num_boats):
                    now += timedelta(hours=1)
                    Run(
                        signup=signup,
                        report=self.report,
                        kind=Run.Kind.BOAT,
                        created_on=now,
                    ).save()
                for _ in range(test.num_breaks):
                    now += timedelta(hours=1)
                    Run(
                        signup=signup,
                        report=self.report,
                        kind=Run.Kind.BREAK,
                        created_on=now,
                    ).save()

                self.pilot.prepaid_flights = test.initial_prepaid_flights
                self.pilot.save()

                if test.price_of_purchase:
                    Purchase(
                        signup=signup,
                        report=self.report,
                        description="Description",
                        price=test.price_of_purchase,
                    ).save()

                bill = Bill(
                    signup=signup, report=self.report, method=PaymentMethods.CASH
                )
                self.assertEqual(
                    bill.num_flights,
                    test.num_flights_with_bus
                    + test.num_flights_with_lift
                    + test.num_flights_with_postbus,
                )
                self.assertEqual(bill.num_flights_with_bus, test.num_flights_with_bus)
                self.assertEqual(bill.num_flights_with_lift, test.num_flights_with_lift)
                self.assertEqual(
                    bill.num_flights_with_postbus, test.num_flights_with_postbus
                )
                self.assertEqual(bill.num_services, test.num_buses + test.num_boats)
                self.assertEqual(
                    bill.to_pay,
                    test.num_flights_to_pay * Bill.PRICE_OF_FLIGHT
                    + test.price_of_purchase,
                )

                bill.prepaid_flights = bill.num_prepaid_flights
                to_pay_before_save = bill.to_pay
                bill.amount = to_pay_before_save
                bill.save()
                self.assertEqual(test.final_prepaid_flights, self.pilot.prepaid_flights)
                self.assertEqual(to_pay_before_save, bill.to_pay)
                self.assertEqual(bill.prepaid_flights, bill.num_prepaid_flights)

                bill.delete()
                self.assertEqual(
                    test.initial_prepaid_flights, self.pilot.prepaid_flights
                )

                # Tear down sub test.
                signup.delete()

    def test_training_orga_receives_extra_service(self):
        signup = Signup.objects.create(pilot=self.pilot, training=self.training)
        bill = Bill(signup=signup, report=self.report, method=PaymentMethods.CASH)
        self.assertEqual(bill.num_services, 0)

        self.report.orga_1 = signup
        self.assertEqual(bill.num_services, 1)

        self.report.orga_1 = None
        self.report.orga_2 = signup
        self.assertEqual(bill.num_services, 1)

    def test_update_does_not_affect_prepaid_flights(self):
        signup = Signup.objects.create(pilot=self.pilot, training=self.training)
        bill = Bill.objects.create(
            signup=signup,
            report=self.report,
            prepaid_flights=2,
            amount=0,
            method=PaymentMethods.CASH,
        )
        self.assertEqual(8, self.pilot.prepaid_flights)

        bill.method = PaymentMethods.TWINT
        bill.save()
        self.assertEqual(8, self.pilot.prepaid_flights)

    def test_create_bill_marks_pilot_not_new(self):
        self.assertTrue(self.pilot.is_new)
        signup = Signup.objects.create(pilot=self.pilot, training=self.training)
        Bill(
            signup=signup,
            report=self.report,
            prepaid_flights=2,
            amount=0,
            method=PaymentMethods.CASH,
        ).save()
        self.assertFalse(self.pilot.is_new)

    def test_was_paid_in_cash(self):
        signup = Signup.objects.create(pilot=self.pilot, training=self.training)
        for method in PaymentMethods:
            with self.subTest(method=method):
                bill = Bill.objects.create(
                    signup=signup,
                    report=self.report,
                    prepaid_flights=0,
                    amount=420,
                    method=method,
                )
                self.assertEqual(method == PaymentMethods.CASH, bill.was_paid_in_cash)
                bill.delete()

    def test_detailed_flights(self):
        for runs, expected_flights in [
            (tuple(), "0"),
            ((Run.Kind.FLIGHT,), "1 (1x🚐)"),
            ((Run.Kind.FLIGHT, Run.Kind.FLIGHT), "2 (2x🚐)"),
            ((Run.Kind.FLIGHT, Run.Kind.FLIGHT_WITH_POSTBUS), "2 (1x🚐, 1x📯)"),
            ((Run.Kind.FLIGHT_WITH_LIFT, Run.Kind.FLIGHT_WITH_POSTBUS), "2 (1x🚡, 1x📯)"),
        ]:
            with self.subTest(runs=runs, expected_flights=expected_flights):
                signup = Signup.objects.create(pilot=self.pilot, training=self.training)
                now = timezone.now()
                for run in runs:
                    now += timedelta(hours=1)
                    Run(
                        signup=signup,
                        report=self.report,
                        kind=run,
                        created_on=now,
                    ).save()
                bill = Bill(
                    signup=signup,
                    report=self.report,
                    prepaid_flights=0,
                    amount=420,
                    method=PaymentMethods.CASH,
                )
                self.assertEqual(bill.detailed_flights, expected_flights)

                # Tear down sub test.
                signup.delete()


class PurchaseTests(TestCase):
    def setUp(self):
        self.pilot = get_user_model().objects.create(
            first_name="Pilot", email="pilot@example.com"
        )
        training = Training.objects.create(date=TODAY)
        self.signup = Signup.objects.create(pilot=self.pilot, training=training)
        self.report = Report.objects.create(training=training, cash_at_start=0)

    def test_is_day_pass(self):
        for item in Purchase.Items:
            with self.subTest(item=item):
                purchase = Purchase.save_item(self.signup, self.report, item)
                self.assertFalse(purchase.is_day_pass)

        purchase = Purchase.save_day_pass(self.signup, self.report)
        self.assertTrue(purchase.is_day_pass)

    def test_is_prepaid_flights(self):
        for item in Purchase.Items:
            with self.subTest(item=item):
                purchase = Purchase.save_item(self.signup, self.report, item)
                self.assertEqual(
                    item == Purchase.Items.PREPAID_FLIGHTS, purchase.is_prepaid_flights
                )

        purchase = Purchase.save_day_pass(self.signup, self.report)
        self.assertFalse(purchase.is_prepaid_flights)

    def test_is_equipment(self):
        for item in Purchase.Items:
            with self.subTest(item=item):
                purchase = Purchase.save_item(self.signup, self.report, item)
                self.assertEqual(
                    item != Purchase.Items.PREPAID_FLIGHTS, purchase.is_equipment
                )

        purchase = Purchase.save_day_pass(self.signup, self.report)
        self.assertFalse(purchase.is_equipment)

    def test_create_and_delete_prepaid_flights(self):
        self.assertEqual(0, self.pilot.prepaid_flights)
        Purchase.save_item(self.signup, self.report, Purchase.Items.PREPAID_FLIGHTS)
        self.assertEqual(10, self.pilot.prepaid_flights)
        Purchase.objects.all().delete()
        self.pilot.refresh_from_db()
        self.assertEqual(0, self.pilot.prepaid_flights)

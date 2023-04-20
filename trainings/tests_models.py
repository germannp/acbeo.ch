from datetime import date, datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import Training, Signup
from bookkeeping.models import Bill, PaymentMethods, Purchase, Report, Run


TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


class TrainingTests(TestCase):
    def setUp(self):
        pilot_a = get_user_model().objects.create(
            email="pilot_a@example.com", role=get_user_model().Role.Member
        )
        pilot_b = get_user_model().objects.create(
            email="pilot_b@example.com", role=get_user_model().Role.Member
        )
        self.training = Training.objects.create(date=TOMORROW, max_pilots=3)
        now = datetime.now()
        self.signup_a = Signup.objects.create(
            pilot=pilot_a, training=self.training, signed_up_on=now
        )
        now += timedelta(seconds=10)
        self.signup_b = Signup.objects.create(
            pilot=pilot_b, training=self.training, signed_up_on=now
        )

    def test_two_and_only_two_spots_are_reserved_for_orgas(self):
        for signup in [self.signup_a, self.signup_b]:
            self.assertEqual(signup.status, Signup.Status.Waiting)

        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
        self.assertEqual(self.signup_a.status, Signup.Status.Selected)
        self.assertEqual(self.signup_b.status, Signup.Status.Waiting)

        orga_1 = get_user_model().objects.create(
            email="orga_1@example.com", role=get_user_model().Role.Orga
        )
        orga_2 = get_user_model().objects.create(
            email="orga_2@example.com", role=get_user_model().Role.Orga
        )
        now = datetime.now() + timedelta(hours=1)
        signup_1 = Signup.objects.create(
            pilot=orga_1, training=self.training, signed_up_on=now
        )
        now += timedelta(seconds=10)
        signup_2 = Signup.objects.create(
            pilot=orga_2, training=self.training, signed_up_on=now
        )
        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b, signup_1, signup_2]:
            signup.refresh_from_db()
        self.assertEqual(self.signup_a.status, Signup.Status.Selected)
        self.assertEqual(self.signup_b.status, Signup.Status.Waiting)
        self.assertEqual(signup_1.status, Signup.Status.Selected)
        self.assertEqual(signup_2.status, Signup.Status.Selected)

        signup_1.cancel()
        signup_1.save()
        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b, signup_1, signup_2]:
            signup.refresh_from_db()
        self.assertEqual(self.signup_a.status, Signup.Status.Selected)
        self.assertEqual(self.signup_b.status, Signup.Status.Waiting)
        self.assertEqual(signup_1.status, Signup.Status.Canceled)
        self.assertEqual(signup_2.status, Signup.Status.Selected)

        signup_1.resignup()
        signup_1.save()
        orga_3 = get_user_model().objects.create(
            email="orga_3@example.com", role=get_user_model().Role.Orga
        )
        now += timedelta(seconds=10)
        signup_3 = Signup.objects.create(
            pilot=orga_3, training=self.training, signed_up_on=now
        )
        self.training.max_pilots += 1
        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b, signup_1, signup_2, signup_3]:
            signup.refresh_from_db()
        self.assertEqual(self.signup_a.status, Signup.Status.Selected)
        self.assertEqual(self.signup_b.status, Signup.Status.Selected)
        self.assertEqual(signup_1.status, Signup.Status.Selected)
        self.assertEqual(signup_2.status, Signup.Status.Selected)
        self.assertEqual(signup_3.status, Signup.Status.Waiting)

    def test_stay_selected_when_max_pilots_is_reduced(self):
        for signup in [self.signup_a, self.signup_b]:
            self.assertEqual(signup.status, Signup.Status.Waiting)

        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
        self.assertEqual(self.signup_a.status, Signup.Status.Selected)
        self.assertEqual(self.signup_b.status, Signup.Status.Waiting)

        self.training.max_pilots += 1
        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
            self.assertEqual(signup.status, Signup.Status.Selected)

        self.training.max_pilots -= 1
        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
            self.assertEqual(signup.status, Signup.Status.Selected)

    def test_only_with_priority_selected_before_priority_date(self):
        self.signup_b.update_is_certain(False)
        self.signup_b.save()
        self.assertTrue(self.signup_a.has_priority)
        self.assertFalse(self.signup_b.has_priority)

        self.training.max_pilots += 1
        self.training.priority_date = TOMORROW
        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
        self.assertEqual(self.signup_a.status, Signup.Status.Selected)
        self.assertEqual(self.signup_b.status, Signup.Status.Waiting)

        self.training.priority_date = TODAY
        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
        self.assertEqual(self.signup_a.status, Signup.Status.Selected)
        self.assertEqual(self.signup_b.status, Signup.Status.Waiting)

        self.training.priority_date = YESTERDAY
        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
            self.assertEqual(signup.status, Signup.Status.Selected)

    def test_stay_selected_when_priority_date_is_moved(self):
        self.signup_b.update_is_certain(False)
        self.signup_b.save()
        self.assertTrue(self.signup_a.has_priority)
        self.assertFalse(self.signup_b.has_priority)

        self.training.max_pilots += 1
        self.training.priority_date = YESTERDAY
        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
            self.assertEqual(signup.status, Signup.Status.Selected)

        self.training.priority_date = TOMORROW
        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
            self.assertEqual(signup.status, Signup.Status.Selected)


class SignupTests(TestCase):
    def setUp(self):
        self.pilot = get_user_model().objects.create(
            email="pilot@example.com", role=get_user_model().Role.Member
        )
        self.training = Training.objects.create(date=TOMORROW, priority_date=TOMORROW)
        self.signup = Signup.objects.create(
            pilot=self.pilot, training=self.training, status=Signup.Status.Selected
        )
        self.time_selected = self.signup.signed_up_on

        self.guest = get_user_model().objects.create(
            email="guest@example.com", role=get_user_model().Role.Guest
        )
        self.guest_signup = Signup.objects.create(
            pilot=self.guest, training=self.training
        )

    def test_member_required_for_priority(self):
        self.assertTrue(self.signup.has_priority)
        self.assertFalse(self.guest_signup.has_priority)

    @mock.patch("trainings.models.datetime")
    def test_resignup_sets_to_waiting_list(self, mocked_datetime):
        mocked_datetime.now.return_value = datetime.now()
        self.assertEqual(self.signup.status, Signup.Status.Selected)

        mocked_datetime.now.return_value += timedelta(seconds=10)
        self.signup.cancel()
        time_of_cancelation = self.signup.signed_up_on
        self.assertLess(self.time_selected, time_of_cancelation)
        self.assertEqual(self.signup.status, Signup.Status.Canceled)

        mocked_datetime.now.return_value += timedelta(seconds=10)
        self.signup.resignup()
        self.assertLess(time_of_cancelation, self.signup.signed_up_on)
        self.assertEqual(self.signup.status, Signup.Status.Waiting)

    @mock.patch("trainings.models.datetime")
    def test_update_is_certain_sets_to_waiting_list_and_removes_priority(
        self, mocked_datetime
    ):
        mocked_datetime.now.return_value = datetime.now()
        self.assertEqual(self.signup.status, Signup.Status.Selected)
        self.assertTrue(self.signup.has_priority)

        mocked_datetime.now.return_value += timedelta(seconds=10)
        self.signup.update_is_certain(False)
        time_of_update_to_uncertain = self.signup.signed_up_on
        self.assertLess(self.time_selected, time_of_update_to_uncertain)
        self.assertEqual(self.signup.status, Signup.Status.Waiting)
        self.assertFalse(self.signup.has_priority)

        mocked_datetime.now.return_value += timedelta(seconds=10)
        self.signup.update_is_certain(True)
        self.assertEqual(time_of_update_to_uncertain, self.signup.signed_up_on)
        self.assertEqual(self.signup.status, Signup.Status.Waiting)
        self.assertTrue(self.signup.has_priority)

    @mock.patch("trainings.models.datetime")
    def test_update_for_time_sets_to_waiting_list_and_removes_priority(
        self, mocked_datetime
    ):
        mocked_datetime.now.return_value = datetime.now()
        self.assertEqual(self.signup.status, Signup.Status.Selected)
        self.assertTrue(self.signup.has_priority)

        mocked_datetime.now.return_value += timedelta(seconds=10)
        self.signup.update_for_time(Signup.Time.ArriveLate)
        time_of_update_to_arrive_late = self.signup.signed_up_on
        self.assertLess(self.time_selected, time_of_update_to_arrive_late)
        self.assertEqual(self.signup.status, Signup.Status.Waiting)
        self.assertFalse(self.signup.has_priority)

        mocked_datetime.now.return_value += timedelta(seconds=10)
        self.signup.update_for_time(Signup.Time.LeaveEarly)
        self.assertEqual(time_of_update_to_arrive_late, self.signup.signed_up_on)
        self.assertEqual(self.signup.status, Signup.Status.Waiting)
        self.assertFalse(self.signup.has_priority)

        mocked_datetime.now.return_value += timedelta(seconds=10)
        self.signup.update_for_time(Signup.Time.Individually)
        self.assertEqual(time_of_update_to_arrive_late, self.signup.signed_up_on)
        self.assertEqual(self.signup.status, Signup.Status.Waiting)
        self.assertFalse(self.signup.has_priority)

        mocked_datetime.now.return_value += timedelta(seconds=10)
        self.signup.update_for_time(Signup.Time.WholeDay)
        self.assertEqual(time_of_update_to_arrive_late, self.signup.signed_up_on)
        self.assertEqual(self.signup.status, Signup.Status.Waiting)
        self.assertTrue(self.signup.has_priority)

    def test_for_sketchy_weather_does_not_affect_status_and_priority(self):
        self.assertTrue(self.signup.for_sketchy_weather)
        self.assertEqual(self.signup.status, Signup.Status.Selected)
        self.assertTrue(self.signup.has_priority)

        self.signup.for_sketchy_weather = False
        self.assertEqual(self.signup.status, Signup.Status.Selected)
        self.assertTrue(self.signup.has_priority)

    def test_is_motivated(self):
        for status, is_certain, for_time, is_motivated in [
            # Cannot be Canceled
            (Signup.Status.Waiting, True, Signup.Time.WholeDay, True),
            (Signup.Status.Selected, True, Signup.Time.WholeDay, True),
            (Signup.Status.Canceled, True, Signup.Time.WholeDay, False),
            # Must be certain
            (Signup.Status.Waiting, False, Signup.Time.WholeDay, False),
            # Must be for whole day
            (Signup.Status.Waiting, True, Signup.Time.ArriveLate, False),
            (Signup.Status.Waiting, True, Signup.Time.LeaveEarly, False),
            (Signup.Status.Waiting, True, Signup.Time.Individually, False),
        ]:
            with self.subTest(
                status=status,
                is_certain=is_certain,
                for_time=for_time,
                is_motivated=is_motivated,
            ):
                self.signup.status = status
                self.signup.is_certain = is_certain
                self.signup.for_time = for_time
                self.assertEqual(self.signup.is_motivated, is_motivated)

    def test_is_cancelable(self):
        report = Report.objects.create(training=self.training, cash_at_start=1337)
        for kind, is_cancelable in [
            (Run.Kind.Flight, False),
            (Run.Kind.Bus, False),
            (Run.Kind.Boat, False),
            (Run.Kind.Break, True),
        ]:
            with self.subTest(kind=kind, is_cancelable=is_cancelable):
                Run.objects.all().delete()
                Run(
                    signup=self.signup,
                    report=report,
                    kind=kind,
                    created_on=timezone.now(),
                ).save()
                self.assertEqual(self.signup.is_cancelable, is_cancelable)

        self.assertTrue(self.signup.is_cancelable)
        Purchase.save_item(self.signup, report, Purchase.Items.LIFEJACKET)
        self.assertFalse(self.signup.is_cancelable)

    def test_is_active(self):
        self.signup.status = Signup.Status.Waiting
        self.assertFalse(self.signup.is_active)

        self.signup.status = Signup.Status.Selected
        self.assertTrue(self.signup.is_active)

        report = Report.objects.create(training=self.training, cash_at_start=1337)
        Bill(
            signup=self.signup,
            report=report,
            prepaid_flights=0,
            amount=10,
            method=PaymentMethods.CASH,
        ).save()
        self.assertFalse(self.signup.is_active)

    def test_must_be_paid(self):
        self.assertFalse(self.signup.must_be_paid)
        report = Report.objects.create(training=self.training, cash_at_start=1337)
        for kind, must_be_paid in [
            (Run.Kind.Flight, True),
            (Run.Kind.Bus, True),
            (Run.Kind.Boat, True),
            (Run.Kind.Break, False),
        ]:
            with self.subTest(kind=kind, must_be_amount=must_be_paid):
                Run.objects.all().delete()
                Run(
                    signup=self.signup,
                    report=report,
                    kind=kind,
                    created_on=timezone.now(),
                ).save()
                self.assertEqual(self.signup.must_be_paid, must_be_paid)

        self.assertFalse(self.signup.must_be_paid)
        Purchase.save_item(self.signup, report, Purchase.Items.LIFEJACKET)
        self.assertTrue(self.signup.must_be_paid)

        Bill(
            signup=self.signup,
            report=report,
            prepaid_flights=0,
            amount=420,
            method=PaymentMethods.CASH,
        ).save()
        self.assertFalse(self.signup.must_be_paid)

    def test_needs_day_pass(self):
        # Guests only need a day pass after the third flight
        training = Training.objects.create(date=date(2000, 9, 15))
        signup = Signup.objects.create(pilot=self.guest, training=training)
        report = Report.objects.create(training=training, cash_at_start=1337)
        now = timezone.now()
        for _ in range(3):
            self.assertFalse(signup.needs_day_pass)
            Run(
                signup=signup,
                report=report,
                kind=Run.Kind.Flight,
                created_on=now,
            ).save()
            now += timedelta(minutes=5)
        self.assertTrue(signup.needs_day_pass)

        Run(
            signup=signup,
            report=report,
            kind=Run.Kind.Boat,
            created_on=now,
        ).save()
        self.assertTrue(signup.needs_day_pass)

        # Guests only need one day pass
        Purchase.save_day_pass(signup, report)
        self.assertFalse(signup.needs_day_pass)
        Purchase.objects.all().delete()

        # Guests only need two day passes in a month
        training = Training.objects.create(date=date(2000, 9, 14))
        prev_signup = Signup.objects.create(pilot=self.guest, training=training)
        Purchase.save_day_pass(prev_signup, report)
        self.assertTrue(signup.needs_day_pass)

        training = Training.objects.create(date=date(2000, 8, 5))
        prev_signup = Signup.objects.create(pilot=self.guest, training=training)
        Purchase.save_day_pass(prev_signup, report)
        self.assertTrue(signup.needs_day_pass)

        training = Training.objects.create(date=date(2000, 9, 5))
        prev_signup = Signup.objects.create(pilot=self.guest, training=training)
        Purchase.save_day_pass(prev_signup, report)
        self.assertFalse(signup.needs_day_pass)

        # Guets only need four day passes per year
        prev_signup.purchases.all().delete()
        self.assertTrue(signup.needs_day_pass)

        training = Training.objects.create(date=date(2000, 1, 1))
        prev_signup = Signup.objects.create(pilot=self.guest, training=training)
        Purchase.save_day_pass(prev_signup, report)
        self.assertTrue(signup.needs_day_pass)

        training = Training.objects.create(date=date(1999, 9, 15))
        prev_signup = Signup.objects.create(pilot=self.guest, training=training)
        Purchase.save_day_pass(prev_signup, report)
        self.assertTrue(signup.needs_day_pass)

        training = Training.objects.create(date=date(2000, 2, 1))
        prev_signup = Signup.objects.create(pilot=self.guest, training=training)
        Purchase.save_day_pass(prev_signup, report)
        self.assertFalse(signup.needs_day_pass)

    def test_is_paid(self):
        report = Report.objects.create(training=self.training, cash_at_start=1337)
        self.assertFalse(self.signup.is_paid)

        Bill(
            signup=self.signup,
            report=report,
            prepaid_flights=0,
            amount=420,
            method=PaymentMethods.CASH,
        ).save()
        self.assertTrue(self.signup.is_paid)

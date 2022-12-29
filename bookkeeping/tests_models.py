from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from django.utils import timezone

from .models import Report, Run
from trainings.models import Signup, Training


TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


class TestRun(SimpleTestCase):
    def setUp(self):
        self.pilot = get_user_model()(first_name="Pilot", email="pilot@example.com")
        training = Training(date=TODAY)
        now = timezone.now()
        Signup(pilot=self.pilot, training=training, signed_up_on=now)
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
                    pilot=self.pilot,
                    report=self.report,
                    kind=kind,
                    created_on=timezone.now(),
                )
                self.assertEqual(run.is_relevant_for_bill, is_relevant_for_bill)

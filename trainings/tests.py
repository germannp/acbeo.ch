from datetime import datetime, timedelta
import locale
import re
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Registration

locale.setlocale(locale.LC_TIME, "de_CH")


class SignupListTests(TestCase):
    def test_past_trainings_not_listed(self):
        pilot = User(username="Pilot")
        pilot.save()

        today = datetime.now().date()
        Registration(pilot=pilot, date=today).save()
        yesterday = today - timedelta(days=1)
        Registration(pilot=pilot, date=yesterday).save()

        self.client.force_login(pilot)
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, yesterday.strftime("%A, %d. %B %Y"))
        self.assertContains(response, today.strftime("%A, %d. %B %Y"))

    def test_showing_either_signup_or_update_button(self):
        pilot_a = User(username="Pilot A")
        pilot_a.save()
        today = datetime.now().date()
        Registration(pilot=pilot_a, date=today).save()

        pilot_b = User(username="Pilot B")
        pilot_b.save()
        tomorrow = today + timedelta(days=1)
        Registration(pilot=pilot_b, date=tomorrow).save()

        self.client.force_login(pilot_a)
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, today.strftime("%A, %d. %B %Y"))
        self.assertContains(response, tomorrow.strftime("%A, %d. %B %Y"))
        self.assertContains(response, f"{today.isoformat()}/update")
        hidden_update_button = re.compile(
            "<!--.{0,100}" + today.isoformat() + "\/signup.{0,100}-->", re.DOTALL
        )
        self.assertIsNotNone(hidden_update_button.search(str(response.content)))

        self.client.force_login(pilot_b)
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, today.strftime("%A, %d. %B %Y"))
        self.assertContains(response, tomorrow.strftime("%A, %d. %B %Y"))
        self.assertContains(response, f"{tomorrow.isoformat()}/update")
        hidden_update_button = re.compile(
            "<!--.{0,100}" + tomorrow.isoformat() + "\/signup.{0,100}-->", re.DOTALL
        )
        self.assertIsNotNone(hidden_update_button.search(str(response.content)))


class SignupTests(TestCase):
    @mock.patch("trainings.views.datetime")
    def test_default_date_is_next_saturday(self, mocked_datetime):
        monday = datetime(2007, 1, 1)
        self.assertEqual(monday.strftime("%A"), "Montag")

        mocked_datetime.now.return_value = monday
        pilot = User(username="Pilot")
        pilot.save()
        self.client.force_login(pilot)
        response = self.client.get(reverse("signup"))
        self.assertContains(response, "2007-01-06")
        self.assertEqual(datetime(2007, 1, 6).strftime("%A"), "Samstag")

    def test_successive_signups(self):
        pilot = User(username="Pilot")
        pilot.save()
        today = datetime.now().date()
        self.client.force_login(pilot)
        response = self.client.post(
            reverse("signup"),
            data={"pilot": pilot.username, "date": today.isoformat()},
            follow=True,
        )
        tomorrow = today + timedelta(days=1)
        self.assertContains(response, tomorrow.isoformat())

    def test_cannot_signup_for_past_training(self):
        pilot = User(username="Pilot")
        pilot.save()
        self.client.force_login(pilot)
        response = self.client.post(
            reverse("signup"), data={"pilot": pilot.username, "date": "2004-12-01"}
        )
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Registration.objects.all()))

    def test_cannot_signup_for_past_more_than_a_year_ahead(self):
        pilot = User(username="Pilot")
        pilot.save()
        self.client.force_login(pilot)
        response = self.client.post(
            reverse("signup"), data={"pilot": pilot.username, "date": "2048-12-01"}
        )
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Registration.objects.all()))

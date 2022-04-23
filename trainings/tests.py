from datetime import datetime, timedelta
import locale
import re
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Singup

locale.setlocale(locale.LC_TIME, "de_CH")


class SignupListTests(TestCase):
    def setUp(self):
        self.pilot = User(username="Pilot")
        self.pilot.save()

        self.today = datetime.now().date()
        self.yesterday = self.today - timedelta(days=1)
        self.tomorrow = self.today + timedelta(days=1)

    def test_past_trainings_not_listed(self):
        Singup(pilot=self.pilot, date=self.today).save()
        Singup(pilot=self.pilot, date=self.yesterday).save()

        self.client.force_login(self.pilot)
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.yesterday.strftime("%A, %d. %B %Y"))
        self.assertContains(response, self.today.strftime("%A, %d. %B %Y"))

    def test_showing_either_signup_or_update_button(self):
        pilot_a = User(username="Pilot A")
        pilot_a.save()
        Singup(pilot=pilot_a, date=self.today).save()

        pilot_b = User(username="Pilot B")
        pilot_b.save()
        Singup(pilot=pilot_b, date=self.tomorrow).save()

        self.client.force_login(pilot_a)
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.today.strftime("%A, %d. %B %Y"))
        self.assertContains(response, self.tomorrow.strftime("%A, %d. %B %Y"))
        self.assertContains(response, f"{self.today.isoformat()}/update")
        hidden_update_button = re.compile(
            "<!--.{0,100}" + self.today.isoformat() + "\/signup.{0,100}-->", re.DOTALL
        )
        self.assertIsNotNone(hidden_update_button.search(str(response.content)))

        self.client.force_login(pilot_b)
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.today.strftime("%A, %d. %B %Y"))
        self.assertContains(response, self.tomorrow.strftime("%A, %d. %B %Y"))
        self.assertContains(response, f"{self.tomorrow.isoformat()}/update")
        hidden_update_button = re.compile(
            "<!--.{0,100}" + self.tomorrow.isoformat() + "\/signup.{0,100}-->",
            re.DOTALL,
        )
        self.assertIsNotNone(hidden_update_button.search(str(response.content)))


class SignupTests(TestCase):
    def setUp(self):
        self.pilot = User(username="Pilot")
        self.pilot.save()
        self.client.force_login(self.pilot)

    @mock.patch("trainings.views.datetime")
    def test_default_date_is_next_saturday(self, mocked_datetime):
        monday = datetime(2007, 1, 1)
        self.assertEqual(monday.strftime("%A"), "Montag")
        saturday = datetime(2007, 1, 6)
        self.assertEqual(saturday.strftime("%A"), "Samstag")
        sunday = datetime(2007, 1, 7)
        self.assertEqual(sunday.strftime("%A"), "Sonntag")
        next_saturday = datetime(2007, 1, 13)
        self.assertEqual(next_saturday.strftime("%A"), "Samstag")

        mocked_datetime.now.return_value = monday
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, saturday.date().isoformat())

        mocked_datetime.now.return_value = saturday
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, saturday.date().isoformat())

        mocked_datetime.now.return_value = sunday
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, next_saturday.date().isoformat())

    def test_successive_signups(self):
        today = datetime.now().date()
        response = self.client.post(
            reverse("signup"),
            data={"pilot": self.pilot.username, "date": today.isoformat()},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        tomorrow = today + timedelta(days=1)
        self.assertContains(response, tomorrow.isoformat())

    def test_cannot_signup_twice(self):
        response = self.client.post(
            reverse("signup"),
            data={
                "pilot": self.pilot.username,
                "date": datetime.now().date().isoformat(),
            },
            follow=True,
        )
        self.assertEqual(1, len(Singup.objects.all()))

        response = self.client.post(
            reverse("signup"),
            data={
                "pilot": self.pilot.username,
                "date": datetime.now().date().isoformat(),
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alert-warning")
        self.assertEqual(1, len(Singup.objects.all()))

    def test_cannot_signup_for_past_training(self):
        response = self.client.post(
            reverse("signup"), data={"pilot": self.pilot.username, "date": "2004-12-01"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Singup.objects.all()))

    def test_cannot_signup_for_past_more_than_a_year_ahead(self):
        response = self.client.post(
            reverse("signup"), data={"pilot": self.pilot.username, "date": "2048-12-01"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Singup.objects.all()))


class SignupUpdateTests(TestCase):
    def setUp(self):
        self.pilot = User(username="Pilot")
        self.pilot.save()
        self.client.force_login(self.pilot)
        self.today = datetime.now().date()
        Singup(pilot=self.pilot, date=self.today, comment="Test comment").save()
        self.yesterday = self.today - timedelta(days=1)
        Singup(pilot=self.pilot, date=self.yesterday).save()

    def test_comment_is_in_form(self):
        response = self.client.get(
            reverse("update", kwargs={"date": self.today.isoformat()})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Test comment"')

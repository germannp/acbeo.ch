from datetime import datetime, timedelta
import locale
import re
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Training, Signup

locale.setlocale(locale.LC_TIME, "de_CH")


class TrainingListTests(TestCase):
    def setUp(self):
        self.pilot_a = User(username="Pilot A")
        self.pilot_a.save()
        self.pilot_b = User(username="Pilot B")
        self.pilot_b.save()

        self.today = datetime.now().date()
        self.yesterday = self.today - timedelta(days=1)
        self.tomorrow = self.today + timedelta(days=1)

        Training(date=self.yesterday).save()
        todays_training = Training(date=self.today)
        todays_training.save()
        tomorrows_training = Training(date=self.tomorrow)
        tomorrows_training.save()

        Signup(pilot=self.pilot_a, training=todays_training).save()
        Signup(pilot=self.pilot_b, training=tomorrows_training).save()

    def test_past_trainings_not_listed(self):
        self.client.force_login(self.pilot_a)
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotContains(response, self.yesterday.strftime("%A, %d. %B %Y"))
        self.assertContains(response, self.today.strftime("%A, %d. %B %Y"))
        self.assertContains(response, self.tomorrow.strftime("%A, %d. %B %Y"))

    def test_showing_either_signup_or_update_button(self):
        self.client.force_login(self.pilot_a)
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, self.today.strftime("%A, %d. %B %Y"))
        self.assertContains(response, self.tomorrow.strftime("%A, %d. %B %Y"))
        self.assertContains(response, f"{self.today.isoformat()}/update")
        hidden_update_button = re.compile(
            "<!--.{0,100}" + self.today.isoformat() + "\/signup.{0,100}-->", re.DOTALL
        )
        self.assertIsNotNone(hidden_update_button.search(str(response.content)))

        self.client.force_login(self.pilot_b)
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, self.today.strftime("%A, %d. %B %Y"))
        self.assertContains(response, self.tomorrow.strftime("%A, %d. %B %Y"))
        self.assertContains(response, f"{self.tomorrow.isoformat()}/update")
        hidden_update_button = re.compile(
            "<!--.{0,100}" + self.tomorrow.isoformat() + "\/signup.{0,100}-->",
            re.DOTALL,
        )
        self.assertIsNotNone(hidden_update_button.search(str(response.content)))


class TrainingUpdateTests(TestCase):
    def setUp(self):
        self.pilot = User(username="Pilot")
        self.pilot.save()
        self.client.force_login(self.pilot)

        self.today = datetime.now().date()
        Training(date=self.today).save()

        self.default_info = "Training findet statt"
        self.info = "Training abgesagt"

    def test_form_is_prefilled(self):
        response = self.client.get(
            reverse("update_training", kwargs={"date": self.today.isoformat()})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.default_info)
        self.assertTemplateUsed(response, "trainings/update_training.html")

        response = self.client.post(
            reverse("update_training", kwargs={"date": self.today.isoformat()}),
            data={"info": self.info},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")

        response = self.client.get(
            reverse("update_training", kwargs={"date": self.today.isoformat()})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.info)
        self.assertTemplateUsed(response, "trainings/update_training.html")

    def test_infos_are_shown_in_list(self):
        response = self.client.get(reverse("trainings"))
        self.assertNotContains(response, self.default_info)
        self.assertNotContains(response, self.info)
        response = self.client.post(
            reverse("update_training", kwargs={"date": self.today.isoformat()}),
            data={"info": self.info},
        )
        response = self.client.get(reverse("trainings"))
        self.assertNotContains(response, self.default_info)
        self.assertContains(response, self.info)


class SingupListTests(TestCase):
    def setUp(self):
        self.pilot_a = User(username="Pilot A")
        self.pilot_a.save()
        self.today = datetime.now().date()
        todays_training = Training(date=self.today)
        todays_training.save()
        Signup(pilot=self.pilot_a, training=todays_training).save()

        self.pilot_b = User(username="Pilot B")
        self.pilot_b.save()
        self.tomorrow = self.today + timedelta(days=1)
        tomorrows_training = Training(date=self.tomorrow)
        tomorrows_training.save()
        Signup(pilot=self.pilot_b, training=tomorrows_training).save()
        self.yesterday = self.today - timedelta(days=1)
        yesterdays_training = Training(date=self.yesterday)
        yesterdays_training.save()
        Signup(pilot=self.pilot_b, training=yesterdays_training).save()
    
    def test_only_my_signups_are_shown(self):
        self.client.force_login(self.pilot_a)
        response = self.client.get(reverse("my_signups"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_signups.html")
        self.assertContains(response, self.today.strftime("%a, %d. %B %Y"))
        self.assertNotContains(response, self.tomorrow.strftime("%a, %d. %B %Y"))
        self.assertNotContains(response, "Vergangene Trainings")
        self.assertNotContains(response, self.yesterday.strftime("%a, %d. %B %Y"))

        self.client.force_login(self.pilot_b)
        response = self.client.get(reverse("my_signups"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_signups.html")
        self.assertContains(response, self.tomorrow.strftime("%a, %d. %B %Y"))
        self.assertNotContains(response, self.today.strftime("%a, %d. %B %Y"))
        self.assertContains(response, "Vergangene Trainings")
        self.assertContains(response, self.yesterday.strftime("%a, %d. %B %Y"))


class SignupCreateTests(TestCase):
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
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, saturday.date().isoformat())

        mocked_datetime.now.return_value = saturday
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, saturday.date().isoformat())

        mocked_datetime.now.return_value = sunday
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, next_saturday.date().isoformat())

    def test_successive_signups(self):
        today = datetime.now().date()
        response = self.client.post(
            reverse("signup"),
            data={"pilot": self.pilot.username, "date": today.isoformat()},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        tomorrow = today + timedelta(days=1)
        self.assertContains(response, tomorrow.isoformat())
        self.assertEqual(1, len(Signup.objects.all()))

    def test_cannot_signup_twice(self):
        response = self.client.post(
            reverse("signup"),
            data={
                "pilot": self.pilot.username,
                "date": datetime.now().date().isoformat(),
            },
            follow=True,
        )
        self.assertEqual(1, len(Signup.objects.all()))

        response = self.client.post(
            reverse("signup"),
            data={
                "pilot": self.pilot.username,
                "date": datetime.now().date().isoformat(),
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(1, len(Signup.objects.all()))

    def test_cannot_signup_for_past_training(self):
        response = self.client.post(
            reverse("signup"), data={"pilot": self.pilot.username, "date": "2004-12-01"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Signup.objects.all()))

    def test_cannot_signup_for_past_more_than_a_year_ahead(self):
        response = self.client.post(
            reverse("signup"), data={"pilot": self.pilot.username, "date": "2048-12-01"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Signup.objects.all()))


class SignupUpdateTests(TestCase):
    def setUp(self):
        self.pilot = User(username="Pilot")
        self.pilot.save()
        self.client.force_login(self.pilot)
        self.today = datetime.now().date()
        training = Training(date=self.today)
        training.save()
        self.signup = Signup(
            pilot=self.pilot, training=training, comment="Test comment"
        )
        self.signup.save()

    def test_comment_is_in_form(self):
        response = self.client.get(
            reverse("update_signup", kwargs={"date": self.today.isoformat()})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, 'value="Test comment"')

    def test_cancel_and_resignup(self):
        self.assertNotEqual(self.signup.status, Signup.Status.Canceled)
        first_signup_time = self.signup.signed_up_on

        response = self.client.post(
            reverse("update_signup", kwargs={"date": self.today.isoformat()}),
            data={"cancel": ""},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, Signup.Status.Canceled)
        self.assertEqual(self.signup.signed_up_on, first_signup_time)

        response = self.client.post(
            reverse("update_signup", kwargs={"date": self.today.isoformat()}),
            data={"resignup": ""},
            follow=True,
        )
        self.signup.refresh_from_db()        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotEqual(self.signup.status, Signup.Status.Canceled)
        self.assertGreater(self.signup.signed_up_on, first_signup_time)

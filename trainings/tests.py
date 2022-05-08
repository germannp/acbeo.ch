from datetime import datetime, timedelta
import locale
import re
from time import sleep
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Training, Signup

locale.setlocale(locale.LC_TIME, "de_CH")

TODAY = datetime.now().date()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


class TrainingListTests(TestCase):
    def setUp(self):
        self.pilot_a = User.objects.create(username="Pilot A")
        self.pilot_b = User.objects.create(username="Pilot B")

        Training(date=YESTERDAY).save()
        todays_training = Training.objects.create(date=TODAY)
        tomorrows_training = Training.objects.create(date=TOMORROW)

        self.signup = Signup.objects.create(
            pilot=self.pilot_a, training=todays_training
        )
        Signup(pilot=self.pilot_b, training=tomorrows_training).save()

    def test_past_trainings_not_listed(self):
        self.client.force_login(self.pilot_a)
        with self.assertNumQueries(7):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotContains(
            response, YESTERDAY.strftime("%A, %d. %B %Y").replace(" 0", " ")
        )
        self.assertContains(
            response, TODAY.strftime("%A, %d. %B %Y").replace(" 0", " ")
        )
        self.assertContains(
            response, TOMORROW.strftime("%A, %d. %B %Y").replace(" 0", " ")
        )

    def test_showing_either_signup_or_update_button(self):
        self.client.force_login(self.pilot_a)
        with self.assertNumQueries(7):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(
            response, TODAY.strftime("%A, %d. %B %Y").replace(" 0", " ")
        )
        self.assertContains(
            response, TOMORROW.strftime("%A, %d. %B %Y").replace(" 0", " ")
        )
        self.assertContains(response, f"{TODAY.isoformat()}/update")
        hidden_update_button = re.compile(
            "<!--.{0,100}" + TODAY.isoformat() + "\/signup.{0,100}-->", re.DOTALL
        )
        self.assertIsNotNone(hidden_update_button.search(str(response.content)))

        self.client.force_login(self.pilot_b)
        with self.assertNumQueries(5):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(
            response, TODAY.strftime("%A, %d. %B %Y").replace(" 0", " ")
        )
        self.assertContains(
            response, TOMORROW.strftime("%A, %d. %B %Y").replace(" 0", " ")
        )
        self.assertContains(response, f"{TOMORROW.isoformat()}/update")
        hidden_update_button = re.compile(
            "<!--.{0,100}" + TOMORROW.isoformat() + "\/signup.{0,100}-->",
            re.DOTALL,
        )
        self.assertIsNotNone(hidden_update_button.search(str(response.content)))

    def test_list_trainings_selects_signups(self):
        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, Signup.Status.Waiting)

        self.client.force_login(self.pilot_a)
        with self.assertNumQueries(7):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")

        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, Signup.Status.Selected)


class TrainingUpdateTests(TestCase):
    def setUp(self):
        self.pilot = User.objects.create(username="Pilot")
        self.client.force_login(self.pilot)

        Training(date=TODAY).save()

        self.default_info = "Training findet statt"
        self.info = "Training abgesagt"

    def test_form_is_prefilled(self):
        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("update_training", kwargs={"date": TODAY.isoformat()})
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_training.html")
        self.assertContains(response, self.default_info)

        with self.assertNumQueries(4 + 4):
            response = self.client.post(
                reverse("update_training", kwargs={"date": TODAY.isoformat()}),
                data={"info": self.info},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, self.info)

        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("update_training", kwargs={"date": TODAY.isoformat()})
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_training.html")
        self.assertContains(response, self.info)

    def test_infos_are_shown_in_list(self):
        with self.assertNumQueries(4):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotContains(response, self.default_info)
        self.assertNotContains(response, self.info)

        with self.assertNumQueries(4 + 4):
            response = self.client.post(
                reverse("update_training", kwargs={"date": TODAY.isoformat()}),
                data={"info": self.info},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotContains(response, self.default_info)
        self.assertContains(response, self.info)

    def test_training_not_found_404(self):
        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("update_training", kwargs={"date": TOMORROW.isoformat()}),
            )
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")


class SingupListTests(TestCase):
    def setUp(self):
        self.pilot_a = User.objects.create(username="Pilot A")
        todays_training = Training.objects.create(date=TODAY)
        self.signup = Signup.objects.create(
            pilot=self.pilot_a, training=todays_training
        )

        self.pilot_b = User.objects.create(username="Pilot B")
        tomorrows_training = Training.objects.create(date=TOMORROW)
        Signup(pilot=self.pilot_b, training=tomorrows_training).save()
        yesterdays_training = Training.objects.create(date=YESTERDAY)
        Signup(pilot=self.pilot_b, training=yesterdays_training).save()

    def test_only_my_signups_are_shown(self):
        self.client.force_login(self.pilot_a)
        with self.assertNumQueries(6):
            response = self.client.get(reverse("my_signups"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_signups.html")
        self.assertContains(
            response, TODAY.strftime("%a, %d. %B %Y").replace(" 0", " ")
        )
        self.assertNotContains(
            response, TOMORROW.strftime("%a, %d. %B %Y").replace(" 0", " ")
        )
        self.assertNotContains(response, "Vergangene Trainings")
        self.assertNotContains(
            response, YESTERDAY.strftime("%a, %d. %B %Y").replace(" 0", " ")
        )

        self.client.force_login(self.pilot_b)
        with self.assertNumQueries(6):
            response = self.client.get(reverse("my_signups"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_signups.html")
        self.assertContains(
            response, TOMORROW.strftime("%a, %d. %B %Y").replace(" 0", " ")
        )
        self.assertNotContains(
            response, TODAY.strftime("%a, %d. %B %Y").replace(" 0", " ")
        )
        self.assertContains(response, "Vergangene Trainings")
        self.assertContains(
            response, YESTERDAY.strftime("%a, %d. %B %Y").replace(" 0", " ")
        )

    def test_list_signups_selects_signups(self):
        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, Signup.Status.Waiting)

        self.client.force_login(self.pilot_a)
        with self.assertNumQueries(6):
            response = self.client.get(reverse("my_signups"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_signups.html")

        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, Signup.Status.Selected)


class SignupCreateTests(TestCase):
    def setUp(self):
        self.pilot = User.objects.create(username="Pilot")
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
        with self.assertNumQueries(2):
            response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, saturday.date().isoformat())

        mocked_datetime.now.return_value = saturday
        with self.assertNumQueries(2):
            response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, saturday.date().isoformat())

        mocked_datetime.now.return_value = sunday
        with self.assertNumQueries(2):
            response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, next_saturday.date().isoformat())

    def test_successive_signups(self):
        with self.assertNumQueries(8):
            response = self.client.post(
                reverse("signup"),
                data={"date": TODAY.isoformat()},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, TOMORROW.isoformat())
        self.assertEqual(1, len(Signup.objects.all()))

    def test_cannot_signup_twice(self):
        with self.assertNumQueries(8):
            response = self.client.post(
                reverse("signup"),
                data={"date": datetime.now().date().isoformat()},
                follow=True,
            )
        self.assertEqual(1, len(Signup.objects.all()))

        with self.assertNumQueries(5):
            response = self.client.post(
                reverse("signup"),
                data={"date": datetime.now().date().isoformat()},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(1, len(Signup.objects.all()))

    def test_cannot_signup_for_past_training(self):
        with self.assertNumQueries(2):
            response = self.client.post(reverse("signup"), data={"date": "2004-12-01"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Signup.objects.all()))

    def test_cannot_signup_more_than_a_year_ahead(self):
        with self.assertNumQueries(2):
            response = self.client.post(reverse("signup"), data={"date": "2048-12-01"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Signup.objects.all()))


class SignupUpdateTests(TestCase):
    def setUp(self):
        self.pilot = User.objects.create(username="Pilot")
        self.client.force_login(self.pilot)
        training = Training.objects.create(date=TODAY)
        self.signup = Signup.objects.create(
            pilot=self.pilot, training=training, comment="Test comment"
        )

    def test_comment_is_in_form_and_can_be_updated(self):
        with self.assertNumQueries(4):
            response = self.client.get(
                reverse("update_signup", kwargs={"date": TODAY.isoformat()})
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, 'value="Test comment"')

        with self.assertNumQueries(11):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY.isoformat()}),
                data={"comment": "Updated comment"},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.signup.refresh_from_db()
        self.assertEqual(self.signup.comment, "Updated comment")

    def test_cannot_update_past_signup(self):
        training = Training.objects.create(date=YESTERDAY)
        signup = Signup.objects.create(pilot=self.pilot, training=training)

        with self.assertNumQueries(4):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": YESTERDAY.isoformat()}),
                data={"comment": "Updated comment"},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, "alert-warning")
        signup.refresh_from_db()
        self.assertNotEqual(signup.comment, "New comment")

    def test_cancel_and_resignup_from_trainings_list(self):
        self.assertNotEqual(self.signup.status, Signup.Status.Canceled)
        first_signup_time = self.signup.signed_up_on

        with self.assertNumQueries(4 + 1 + 5):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY.isoformat()}),
                data={"cancel": ""},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "bi-x-octagon")
        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, Signup.Status.Canceled)
        self.assertEqual(self.signup.signed_up_on, first_signup_time)

        with self.assertNumQueries(4 + 1 + 5 + 1):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY.isoformat()}),
                data={"resignup": ""},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "bi-cloud-check")
        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, Signup.Status.Selected)
        self.assertGreater(self.signup.signed_up_on, first_signup_time)

    def test_cancel_and_resignup_from_signups_list(self):
        self.assertNotEqual(self.signup.status, Signup.Status.Canceled)
        first_signup_time = self.signup.signed_up_on

        with self.assertNumQueries(4 + 1 + 5):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY.isoformat()})
                + "?next="
                + reverse("my_signups"),
                data={"cancel": ""},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_signups.html")
        self.assertContains(response, "bi-x-octagon")
        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, Signup.Status.Canceled)
        self.assertEqual(self.signup.signed_up_on, first_signup_time)

        with self.assertNumQueries(4 + 1 + 5 + 1):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY.isoformat()})
                + "?next="
                + reverse("my_signups"),
                data={"resignup": ""},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_signups.html")
        self.assertContains(response, "bi-cloud-check")
        self.signup.refresh_from_db()
        self.assertNotEqual(self.signup.status, Signup.Status.Canceled)
        self.assertGreater(self.signup.signed_up_on, first_signup_time)

    def test_next_urls(self):
        trainings_url = reverse("trainings")
        my_signups_url = reverse("my_signups")

        with self.assertNumQueries(6):
            response = self.client.get(trainings_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotContains(response, "/update-signup/?next=" + my_signups_url)

        with self.assertNumQueries(5):
            response = self.client.get(my_signups_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_signups.html")
        self.assertContains(response, "/update-signup/?next=" + my_signups_url)

        response = self.client.post(
            reverse("update_signup", kwargs={"date": TODAY.isoformat()})
            + "?next=http://danger.com",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")

    def test_signup_not_found_404(self):
        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("update_signup", kwargs={"date": TOMORROW.isoformat()})
            )
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")

        Training(date=TOMORROW).save()
        with self.assertNumQueries(4):
            response = self.client.get(
                reverse("update_signup", kwargs={"date": TOMORROW.isoformat()}),
            )
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")


class SignupSelectionTests(TestCase):
    def setUp(self):
        pilot_a = User.objects.create(username="Pilot A")
        pilot_b = User.objects.create(username="Pilot B")
        self.training = Training.objects.create(date=TODAY, max_pilots=1)
        self.signup_a = Signup.objects.create(pilot=pilot_a, training=self.training)
        sleep(0.001)
        self.signup_b = Signup.objects.create(pilot=pilot_b, training=self.training)

    def test_waiting_after_resignup(self):
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
            self.assertEqual(signup.status, Signup.Status.Waiting)

        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
        self.assertEqual(self.signup_a.status, Signup.Status.Selected)
        self.assertEqual(self.signup_b.status, Signup.Status.Waiting)
        self.assertLess(self.signup_a.signed_up_on, self.signup_b.signed_up_on)

        self.signup_a.cancel()
        self.signup_a.save()
        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
        self.assertEqual(self.signup_a.status, Signup.Status.Canceled)
        self.assertEqual(self.signup_b.status, Signup.Status.Selected)
        self.assertLess(self.signup_a.signed_up_on, self.signup_b.signed_up_on)

        self.signup_a.resignup()
        self.signup_a.save()
        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
        self.assertEqual(self.signup_a.status, Signup.Status.Waiting)
        self.assertEqual(self.signup_b.status, Signup.Status.Selected)
        self.assertGreater(self.signup_a.signed_up_on, self.signup_b.signed_up_on)

    def test_stay_selected_when_max_pilots_is_reduced(self):
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
            self.assertEqual(signup.status, Signup.Status.Waiting)

        self.training.max_pilots = 2
        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
            self.assertEqual(signup.status, Signup.Status.Selected)

        self.training.max_pilots = 1
        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
            self.assertEqual(signup.status, Signup.Status.Selected)

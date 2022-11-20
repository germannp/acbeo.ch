import datetime
from datetime import date, timedelta
from http import HTTPStatus
import locale
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Training, Signup

locale.setlocale(locale.LC_TIME, "de_CH")

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


class SingupListViewTests(TestCase):
    def setUp(self):
        self.pilot_a = get_user_model().objects.create(email="pilot_a@example.com")
        self.client.force_login(self.pilot_a)
        self.todays_training = Training.objects.create(date=TODAY)
        self.signup = Signup.objects.create(
            pilot=self.pilot_a, training=self.todays_training
        )

        self.pilot_b = get_user_model().objects.create(email="pilot_b@example.com")
        Signup(pilot=self.pilot_b, training=self.todays_training).save()
        tomorrows_training = Training.objects.create(date=TOMORROW)
        Signup(pilot=self.pilot_b, training=tomorrows_training).save()
        yesterdays_training = Training.objects.create(date=YESTERDAY)
        Signup(pilot=self.pilot_b, training=yesterdays_training).save()

    def test_only_my_signups_are_shown(self):
        with self.assertNumQueries(9):
            response = self.client.get(reverse("my_signups"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_my_signups.html")
        self.assertContains(
            response,
            TODAY.strftime("%a., %d. %b. %Y").replace(" 0", " ").replace("..", "."),
        )
        self.assertNotContains(
            response,
            TOMORROW.strftime("%a., %d. %b. %Y").replace(" 0", " ").replace("..", "."),
        )
        self.assertNotContains(response, "Vergangene Trainings")
        self.assertNotContains(
            response,
            YESTERDAY.strftime("%a., %d. %b. %Y").replace(" 0", " ").replace("..", "."),
        )

        self.client.force_login(self.pilot_b)
        with self.assertNumQueries(8):
            response = self.client.get(reverse("my_signups"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_my_signups.html")
        self.assertContains(
            response,
            TOMORROW.strftime("%a., %d. %b. %Y").replace(" 0", " ").replace("..", "."),
        )
        self.assertContains(
            response,
            TODAY.strftime("%a., %d. %b. %Y").replace(" 0", " ").replace("..", "."),
        )
        self.assertContains(response, "Vergangene Trainings")
        self.assertContains(
            response,
            YESTERDAY.strftime("%a., %d. %b. %Y").replace(" 0", " ").replace("..", "."),
        )

    def test_list_signups_selects_signups(self):
        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, Signup.Status.Waiting)

        with self.assertNumQueries(9):
            response = self.client.get(reverse("my_signups"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_my_signups.html")

        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, Signup.Status.Selected)

    def test_text_color(self):
        # Trainings with less than 6 motivated pilots
        self.todays_training.select_signups()
        for i in range(3, 8):
            pilot = get_user_model().objects.create(email=f"{i}@example.com")
            Signup(pilot=pilot, training=self.todays_training).save()
            self.assertEqual(i, len(self.todays_training.signups.all()))
            with self.assertNumQueries(8):
                response = self.client.get(reverse("my_signups"))
            self.assertEqual(response.status_code, HTTPStatus.OK)
            self.assertTemplateUsed(response, "trainings/list_my_signups.html")
            self.assertContains(response, i)
            if i < 6:
                self.assertContains(response, "text-warning")
            else:
                self.assertNotContains(response, "text-warning")

        # Signups that are not is_certain and for WholeDay
        for is_certain, for_time, warning in [
            (True, Signup.Time.WholeDay, False),
            (False, Signup.Time.WholeDay, True),
            (True, Signup.Time.ArriveLate, True),
            (True, Signup.Time.LeaveEarly, True),
            (True, Signup.Time.Individually, True),
        ]:
            with self.subTest(
                is_certain=is_certain, for_time=for_time, warning=warning
            ):
                self.signup.is_certain = is_certain
                self.signup.for_time = for_time
                self.signup.save()
                with self.assertNumQueries(8):
                    response = self.client.get(reverse("my_signups"))
                self.assertEqual(response.status_code, HTTPStatus.OK)
                self.assertTemplateUsed(response, "trainings/list_my_signups.html")
                self.assertNotContains(response, "bi-hourglass-split")
                if warning:
                    self.assertContains(response, "text-warning")
                else:
                    self.assertNotContains(response, "text-warning")

        for status, muted in [
            (Signup.Status.Selected, False),
            (Signup.Status.Canceled, True),
        ]:
            with self.subTest(status=status, muted=muted):
                self.signup.status = status
                self.signup.save()
                with self.assertNumQueries(7):
                    response = self.client.get(reverse("my_signups"))
                self.assertEqual(response.status_code, HTTPStatus.OK)
                self.assertTemplateUsed(response, "trainings/list_my_signups.html")
                self.assertNotContains(response, "bi-hourglass-split")
                if muted:
                    self.assertContains(response, "text-muted")
                else:
                    self.assertNotContains(response, "text-muted")


class SignupCreateViewTests(TestCase):
    def setUp(self):
        self.pilot = get_user_model().objects.create(email="pilot@example.com")
        self.client.force_login(self.pilot)

        self.monday = date(2007, 1, 1)
        self.assertEqual(self.monday.strftime("%A"), "Montag")
        self.wednesday = date(2007, 1, 3)
        self.assertEqual(self.wednesday.strftime("%A"), "Mittwoch")
        self.friday = date(2007, 1, 5)
        self.assertEqual(self.friday.strftime("%A"), "Freitag")
        self.saturday = date(2007, 1, 6)
        self.assertEqual(self.saturday.strftime("%A"), "Samstag")
        self.sunday = date(2007, 1, 7)
        self.assertEqual(self.sunday.strftime("%A"), "Sonntag")
        self.next_monday = date(2007, 1, 8)
        self.assertEqual(self.next_monday.strftime("%A"), "Montag")
        self.next_saturday = date(2007, 1, 13)
        self.assertEqual(self.next_saturday.strftime("%A"), "Samstag")

    @mock.patch("trainings.views.date")
    @mock.patch("trainings.views.reverse_lazy")
    def test_default_date_is_next_saturday(self, mocked_reverse, mocked_date):
        mocked_reverse.return_value = ""
        for now, default_date in [
            (self.monday, self.saturday),
            (self.wednesday, self.saturday),
            (self.friday, self.saturday),
            (self.saturday, self.saturday),
            (self.sunday, self.sunday),
            (self.next_monday, self.next_saturday),
        ]:
            with self.subTest(
                now=now.isoformat(), default_date=default_date.isoformat()
            ):
                mocked_date.today.return_value = now
                with self.assertNumQueries(2):
                    response = self.client.get(reverse("signup"))
                self.assertEqual(response.status_code, HTTPStatus.OK)
                self.assertTemplateUsed(response, "trainings/signup.html")
                self.assertContains(response, default_date.isoformat())

    @mock.patch("trainings.forms.date", wraps=date)
    @mock.patch("trainings.views.date", wraps=date)
    def test_default_priority_date_is_wednesday_before_training(
        self, views_date, forms_date
    ):
        views_date.today.return_value = self.monday
        forms_date.today.return_value = self.monday
        dates = [
            self.wednesday,
            self.saturday,
            self.sunday,
            self.next_monday,
            self.next_saturday,
        ]
        for date in dates:
            with self.assertNumQueries(6):
                self.client.post(
                    reverse("signup"),
                    data={"date": date, "for_time": Signup.Time.WholeDay},
                )

        trainings = Training.objects.all()
        self.assertEqual(len(trainings), len(dates))
        for date, training in zip(dates, trainings):
            self.assertEqual(date, training.date)
            self.assertEqual("Mittwoch", training.priority_date.strftime("%A"))
            self.assertLess(training.priority_date, training.date)
            self.assertLessEqual(
                training.date - training.priority_date, timedelta(days=7)
            )

    def test_cannot_signup_twice(self):
        with self.assertNumQueries(8):
            response = self.client.post(
                reverse("signup"),
                data={"date": TODAY, "for_time": Signup.Time.WholeDay},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, "alert-success")
        self.assertContains(response, f"<b>{TODAY.strftime('%A')}</b>")
        self.assertEqual(1, len(Signup.objects.all()))

        with self.assertNumQueries(5):
            response = self.client.post(
                reverse("signup"),
                data={"date": TODAY, "for_time": Signup.Time.WholeDay},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, "alert-warning")
        self.assertContains(response, f"<b>{TODAY.strftime('%A')}</b>")
        self.assertEqual(1, len(Signup.objects.all()))

    def test_cannot_signup_for_past_training(self):
        with self.assertNumQueries(2):
            response = self.client.post(reverse("signup"), data={"date": "2004-12-01"})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Signup.objects.all()))

    def test_cannot_signup_more_than_a_year_ahead(self):
        with self.assertNumQueries(2):
            response = self.client.post(reverse("signup"), data={"date": "2048-12-01"})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Signup.objects.all()))

    def test_cannot_signup_for_non_existent_date(self):
        with self.assertNumQueries(2):
            response = self.client.get(
                reverse("signup", kwargs={"date": "2022-13-13"}),
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

    def test_next_urls(self):
        response = self.client.get(
            reverse("signup", kwargs={"date": TODAY}) + f"?page=2&training=3",
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, reverse("trainings") + "?page=2#training_3")

        with self.assertNumQueries(8):
            response = self.client.post(
                reverse("signup"),
                data={"date": TODAY, "for_time": Signup.Time.WholeDay},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, TOMORROW.isoformat())
        self.assertEqual(1, len(Signup.objects.all()))


class SignupUpdateViewTests(TestCase):
    def setUp(self):
        self.pilot = get_user_model().objects.create(email="pilot@example.com")
        self.client.force_login(self.pilot)
        training = Training.objects.create(date=TODAY)
        self.signup = Signup.objects.create(
            pilot=self.pilot, training=training, comment="Test comment"
        )

    def test_day_is_displayed(self):
        with self.assertNumQueries(5):
            response = self.client.get(reverse("update_signup", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, TODAY.strftime("%A, %d. %B").replace(" 0", " "))

    def test_comment_is_in_form_and_can_be_updated(self):
        with self.assertNumQueries(5):
            response = self.client.get(reverse("update_signup", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, 'value="Test comment"')

        with self.assertNumQueries(15):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY}),
                data={"for_time": self.signup.for_time, "comment": "Updated comment"},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.signup.refresh_from_db()
        self.assertContains(response, "Updated comment")
        self.assertEqual(self.signup.comment, "Updated comment")

    def test_cancel_and_resignup_from_trainings_list(self):
        with self.assertNumQueries(10):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "100%")
        self.assertContains(response, "Ganzer Tag")
        self.assertContains(response, "bi-cloud-haze2-fill")
        self.assertContains(response, "Test comment")

        with self.assertNumQueries(14):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY}),
                data={
                    "cancel": "",
                    # I don't understand why I have to send the choices, but not comment
                    "is_certain": self.signup.is_certain,
                    "for_time": self.signup.for_time,
                    "for_sketchy_weather": self.signup.for_sketchy_weather,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "bi-x-octagon")
        self.assertNotContains(response, "%")
        self.assertNotContains(response, "Ganzer Tag")
        self.assertNotContains(response, "bi-cloud-haze2-fill")
        self.assertContains(response, "Test comment")

        with self.assertNumQueries(15):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY}),
                data={
                    "resignup": "",
                    "is_certain": self.signup.is_certain,
                    "for_time": self.signup.for_time,
                    "for_sketchy_weather": self.signup.for_sketchy_weather,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "bi-cloud-check")
        self.assertTrue(self.signup.is_certain)
        self.assertContains(response, "100%")
        self.assertContains(response, "bi-cloud-haze2-fill")
        self.assertContains(response, "Test comment")

    def test_cancel_and_resignup_from_signups_list(self):
        with self.assertNumQueries(12):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY})
                + "?next="
                + reverse("my_signups"),
                data={
                    "cancel": "",
                    "is_certain": self.signup.is_certain,
                    "for_time": self.signup.for_time,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_my_signups.html")
        self.assertContains(response, "bi-x-octagon")

        with self.assertNumQueries(13):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY})
                + "?next="
                + reverse("my_signups"),
                data={"resignup": "", "for_time": self.signup.for_time},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_my_signups.html")
        self.assertContains(response, "bi-cloud-check")

    def test_update_is_certain(self):
        with self.assertNumQueries(10):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "100%")

        with self.assertNumQueries(5):
            response = self.client.get(reverse("update_signup", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, 'name="is_certain"')

        with self.assertNumQueries(15):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY}),
                data={"is_certain": False, "for_time": self.signup.for_time},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "75%")

    def test_update_for_time(self):
        with self.assertNumQueries(10):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "Ganzer Tag")

        with self.assertNumQueries(5):
            response = self.client.get(reverse("update_signup", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, 'name="for_time"')

        with self.assertNumQueries(15):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY}),
                data={
                    "is_certain": self.signup.is_certain,
                    "for_time": Signup.Time.ArriveLate,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "Kommt später")

    def test_update_for_sketchy_weather(self):
        with self.assertNumQueries(10):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "bi-cloud-haze2-fill")
        self.assertNotContains(response, "bi-sun")

        with self.assertNumQueries(5):
            response = self.client.get(reverse("update_signup", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, 'name="for_sketchy_weather"')

        with self.assertNumQueries(14):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY}),
                data={
                    "is_certain": self.signup.is_certain,
                    "for_sketchy_weather": "False",
                    "for_time": self.signup.for_time,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotContains(response, "bi-cloud-haze2-fill")
        self.assertContains(response, "bi-sun")

    def test_next_urls(self):
        response = self.client.get(
            reverse("update_signup", kwargs={"date": TODAY})
            + f"?next={reverse('trainings')}&page=2&training=3",
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, reverse("trainings") + "?page=2#training_3")

        response = self.client.post(
            reverse("update_signup", kwargs={"date": TODAY})
            + "?next=http://danger.com",
            data={"for_time": Signup.Time.WholeDay},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")

    def test_cannot_update_past_or_non_existent_signup(self):
        training = Training.objects.create(date=YESTERDAY)
        Signup(pilot=self.pilot, training=training).save()
        with self.assertNumQueries(2):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": YESTERDAY}),
                data={"for_time": self.signup.for_time, "comment": "Updated comment"},
                follow=True,
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        with self.assertNumQueries(2):
            response = self.client.get(
                reverse("update_signup", kwargs={"date": "2022-13-13"})
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("update_signup", kwargs={"date": TOMORROW})
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        Training(date=TOMORROW).save()
        with self.assertNumQueries(4):
            response = self.client.get(
                reverse("update_signup", kwargs={"date": TOMORROW}),
            )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

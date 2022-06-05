from datetime import datetime, timedelta
import locale
from time import sleep
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
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
        self.client.force_login(self.pilot_a)

        Training(date=YESTERDAY).save()
        self.todays_training = Training.objects.create(date=TODAY)
        tomorrows_training = Training.objects.create(date=TOMORROW)
        Training.objects.create(date=TOMORROW + timedelta(days=1))
        Training.objects.create(date=TOMORROW + timedelta(days=2))

        self.signup = Signup.objects.create(
            pilot=self.pilot_a, training=self.todays_training
        )
        Signup(pilot=self.pilot_b, training=tomorrows_training).save()

    def test_past_trainings_not_listed(self):
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
        self.assertContains(response, reverse("update_signup", kwargs={"date": TODAY}))
        self.assertNotContains(response, reverse("signup", kwargs={"date": TODAY}))
        self.assertContains(response, reverse("signup", kwargs={"date": TOMORROW}))

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
        self.assertContains(response, reverse("signup", kwargs={"date": TODAY}))
        self.assertContains(
            response, reverse("update_signup", kwargs={"date": TOMORROW})
        )
        self.assertNotContains(response, reverse("signup", kwargs={"date": TOMORROW}))

    def test_list_trainings_selects_signups(self):
        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, Signup.Status.Waiting)

        with self.assertNumQueries(7):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")

        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, Signup.Status.Selected)

    def test_update_info_and_emergency_mail_buttons_shown_and_disabled(self):
        with self.assertNumQueries(7):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        for i in range(3):
            date = TODAY + timedelta(days=i)
            self.assertContains(
                response, reverse("emergency_mail", kwargs={"date": date})
            )
            self.assertContains(
                response,
                reverse("update_training", kwargs={"date": date}),
            )
        date = TODAY + timedelta(days=3)
        self.assertNotContains(
            response, reverse("emergency_mail", kwargs={"date": date})
        )
        self.assertContains(response, reverse("update_training", kwargs={"date": date}))

        self.assertNotContains(response, "disabled")
        self.todays_training.emergency_mail_sender = self.pilot_a
        self.todays_training.save()
        with self.assertNumQueries(6):
            response = self.client.get(reverse("trainings"))
        self.assertContains(response, "disabled")


class TrainingUpdateTests(TestCase):
    def setUp(self):
        self.pilot = User.objects.create(username="Pilot")
        self.client.force_login(self.pilot)

        self.max_pilots = 13
        Training(date=TODAY, max_pilots=self.max_pilots).save()

        self.default_info = "Training findet statt"
        self.info = "Training abgesagt"

    def test_form_is_prefilled(self):
        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("update_training", kwargs={"date": TODAY})
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_training.html")
        self.assertContains(response, self.default_info)
        self.assertContains(response, self.max_pilots)

        with self.assertNumQueries(4 + 4):
            response = self.client.post(
                reverse("update_training", kwargs={"date": TODAY}),
                data={"info": self.info, "max_pilots": self.max_pilots},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, self.info)

        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("update_training", kwargs={"date": TODAY})
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_training.html")
        self.assertContains(response, self.info)
    
    def test_max_pilots_range(self):
        with self.assertNumQueries(3):
            response = self.client.post(
                reverse("update_training", kwargs={"date": TODAY}),
                data={"info": self.info, "max_pilots": 5},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_training.html")
        self.assertContains(response, self.info)
        self.assertContains(response, "alert-warning")

        with self.assertNumQueries(3):
            response = self.client.post(
                reverse("update_training", kwargs={"date": TODAY}),
                data={"info": self.info, "max_pilots": 22},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_training.html")
        self.assertContains(response, self.info)
        self.assertContains(response, "alert-warning")

    def test_infos_are_shown_in_list(self):
        with self.assertNumQueries(4):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotContains(response, self.default_info)
        self.assertNotContains(response, self.info)

        with self.assertNumQueries(4 + 4):
            response = self.client.post(
                reverse("update_training", kwargs={"date": TODAY}),
                data={"info": self.info, "max_pilots": self.max_pilots},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotContains(response, self.default_info)
        self.assertContains(response, self.info)

    def test_training_not_found_404(self):
        with self.assertNumQueries(2):
            response = self.client.get(
                reverse("update_training", kwargs={"date": "2022-13-13"}),
            )
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")

        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("update_training", kwargs={"date": TOMORROW}),
            )
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")


class EmergencyMailTests(TestCase):
    def setUp(self):
        self.pilot_a = User.objects.create(
            username="Pilot A", first_name="Name A", email="sender@example.com"
        )
        self.client.force_login(self.pilot_a)
        self.pilot_b = User.objects.create(username="Pilot B", first_name="Name B")
        self.pilot_c = User.objects.create(username="Pilot C", first_name="Name C")

        self.todays_training = Training.objects.create(date=TODAY)
        self.signup_a_today = Signup.objects.create(
            pilot=self.pilot_a, training=self.todays_training
        )
        Signup(pilot=self.pilot_b, training=self.todays_training).save()
        Signup(pilot=self.pilot_c, training=self.todays_training).save()
        self.todays_training.select_signups()

        yesterdays_training = Training.objects.create(date=YESTERDAY)
        Signup.objects.create(pilot=self.pilot_a, training=yesterdays_training).save()
        Signup.objects.create(pilot=self.pilot_b, training=yesterdays_training).save()
        yesterdays_training.select_signups()

        self.in_a_week = TODAY + timedelta(days=7)
        training_in_a_week = Training.objects.create(date=self.in_a_week)
        Signup(pilot=self.pilot_a, training=training_in_a_week).save()
        Signup(pilot=self.pilot_b, training=training_in_a_week).save()
        training_in_a_week.select_signups()

    def test_sending_emergency_mail(self):
        with self.assertNumQueries(5 + 6):
            response = self.client.post(
                reverse("emergency_mail", kwargs={"date": TODAY}),
                data={"start": "2", "end": "5", "emergency_contacts": ["1", "2"]},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "Seepolizeimail abgesendet.")
        self.assertEqual(1, len(mail.outbox))
        self.assertTrue(
            TODAY.strftime("%A, %d. %B").replace(" 0", " ") in mail.outbox[0].subject
        )
        self.assertEqual(mail.outbox[0].from_email, "info@example.com")
        self.assertTrue(self.pilot_a.email in mail.outbox[0].to)
        self.assertTrue("8:30 bis 20:00" in mail.outbox[0].body)
        self.assertTrue(self.pilot_a.first_name in mail.outbox[0].body)
        self.assertTrue(self.pilot_b.first_name in mail.outbox[0].body)
        self.assertTrue(self.pilot_c.first_name not in mail.outbox[0].body)

        self.todays_training.refresh_from_db()
        self.assertTrue(self.todays_training.emergency_mail_sender == self.pilot_a)

    def test_only_selected_signups_can_be_chosen(self):
        with self.assertNumQueries(5):
            response = self.client.get(
                reverse("emergency_mail", kwargs={"date": TODAY})
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(response, self.pilot_a.first_name)
        self.assertContains(response, self.pilot_b.first_name)
        self.assertContains(response, self.pilot_c.first_name)

        self.signup_a_today.cancel()
        self.signup_a_today.save()
        with self.assertNumQueries(5):
            response = self.client.get(
                reverse("emergency_mail", kwargs={"date": TODAY})
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertNotContains(response, self.pilot_a.first_name)
        self.assertContains(response, self.pilot_b.first_name)
        self.assertContains(response, self.pilot_c.first_name)

        with self.assertNumQueries(6):
            response = self.client.post(
                reverse("emergency_mail", kwargs={"date": TODAY}),
                data={"start": "2", "end": "5", "emergency_contacts": ["1", "2"]},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(response, "Bitte eine gültige Auswahl treffen.")

    def test_cannot_send_emergency_mail_for_past_or_far_ahead_trainings(self):
        with self.assertNumQueries(6):
            response = self.client.post(
                reverse("emergency_mail", kwargs={"date": YESTERDAY}),
                data={"start": "2", "end": "5", "emergency_contacts": ["4", "5"]},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(
            response,
            "Seepolizeimail kann nicht für vergangene Trainings versandt werden.",
        )

        with self.assertNumQueries(6):
            response = self.client.post(
                reverse("emergency_mail", kwargs={"date": self.in_a_week}),
                data={"start": "2", "end": "5", "emergency_contacts": ["6", "7"]},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(
            response,
            "Seepolizeimail kann höchstens drei Tage im Voraus versandt werden.",
        )

    def test_exactly_two_emergency_contacts_must_be_selected(self):
        with self.assertNumQueries(6):
            response = self.client.post(
                reverse("emergency_mail", kwargs={"date": TODAY}),
                data={"start": "2", "end": "5", "emergency_contacts": ["1"]},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(response, "Bitte genau zwei Notfallkontakte ausgewählen.")

        with self.assertNumQueries(6):
            response = self.client.post(
                reverse("emergency_mail", kwargs={"date": TODAY}),
                data={"start": "2", "end": "5", "emergency_contacts": ["1", "2", "3"]},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(response, "Bitte genau zwei Notfallkontakte ausgewählen.")

    def test_cannot_send_emergency_mail_for_non_existing_trainings_404(self):
        with self.assertNumQueries(2):
            response = self.client.get(
                reverse("emergency_mail", kwargs={"date": "2022-13-13"})
            )
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")

        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("emergency_mail", kwargs={"date": TOMORROW})
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
                reverse("signup"), data={"date": TODAY}, follow=True
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, TOMORROW.isoformat())
        self.assertEqual(1, len(Signup.objects.all()))

    def test_cannot_signup_twice(self):
        with self.assertNumQueries(8):
            response = self.client.post(
                reverse("signup"), data={"date": datetime.now().date()}, follow=True
            )
        self.assertEqual(1, len(Signup.objects.all()))

        with self.assertNumQueries(5):
            response = self.client.post(
                reverse("signup"), data={"date": datetime.now().date()}, follow=True
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

    def test_cannot_signup_for_nonexistant_date_404(self):
        with self.assertNumQueries(2):
            response = self.client.get(
                reverse("signup", kwargs={"date": "2022-13-13"}),
            )
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")


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
            response = self.client.get(reverse("update_signup", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, 'value="Test comment"')

        with self.assertNumQueries(11):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY}),
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
                reverse("update_signup", kwargs={"date": YESTERDAY}),
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
                reverse("update_signup", kwargs={"date": TODAY}),
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
                reverse("update_signup", kwargs={"date": TODAY}),
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
                reverse("update_signup", kwargs={"date": TODAY})
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
                reverse("update_signup", kwargs={"date": TODAY})
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
        self.assertNotContains(
            response,
            reverse("update_signup", kwargs={"date": TODAY})
            + "?next="
            + my_signups_url,
        )

        with self.assertNumQueries(5):
            response = self.client.get(my_signups_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_signups.html")
        self.assertContains(
            response,
            reverse("update_signup", kwargs={"date": TODAY})
            + "?next="
            + my_signups_url,
        )

        response = self.client.post(
            reverse("update_signup", kwargs={"date": TODAY})
            + "?next=http://danger.com",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")

    def test_signup_not_found_404(self):
        with self.assertNumQueries(2):
            response = self.client.get(
                reverse("update_signup", kwargs={"date": "2022-13-13"})
            )
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")

        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("update_signup", kwargs={"date": TOMORROW})
            )
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")

        Training(date=TOMORROW).save()
        with self.assertNumQueries(4):
            response = self.client.get(
                reverse("update_signup", kwargs={"date": TOMORROW}),
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

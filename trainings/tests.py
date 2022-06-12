import datetime
from datetime import date, timedelta
import locale
from time import sleep
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .models import Training, Signup

locale.setlocale(locale.LC_TIME, "de_CH")

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


class TrainingTests(TestCase):
    def setUp(self):
        pilot_a = User.objects.create(username="Pilot A")
        pilot_b = User.objects.create(username="Pilot B")
        self.training = Training.objects.create(date=TOMORROW, max_pilots=1)
        self.signup_a = Signup.objects.create(pilot=pilot_a, training=self.training)
        self.signup_b = Signup.objects.create(pilot=pilot_b, training=self.training)

    def test_stay_selected_when_max_pilots_is_reduced(self):
        for signup in [self.signup_a, self.signup_b]:
            self.assertEqual(signup.status, Signup.Status.Waiting)

        self.training.select_signups()
        for signup in [self.signup_a, self.signup_b]:
            signup.refresh_from_db()
        self.assertEqual(self.signup_a.status, Signup.Status.Selected)
        self.assertEqual(self.signup_b.status, Signup.Status.Waiting)

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

    def test_only_with_priority_selected_before_priority_date(self):
        self.signup_b.update_is_certain(False)
        self.signup_b.save()
        self.assertTrue(self.signup_a.has_priority())
        self.assertFalse(self.signup_b.has_priority())

        self.training.max_pilots = 2
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
        self.assertTrue(self.signup_a.has_priority())
        self.assertFalse(self.signup_b.has_priority())

        self.training.max_pilots = 2
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
        pilot = User.objects.create(username="Pilot")
        training = Training.objects.create(date=TOMORROW, priority_date=TOMORROW)
        self.signup = Signup.objects.create(
            pilot=pilot, training=training, status=Signup.Status.Selected
        )
        self.time_selected = self.signup.signed_up_on
        sleep(0.001)

    def test_resignup_sets_to_waiting_list(self):
        self.assertEqual(self.signup.status, Signup.Status.Selected)

        self.signup.cancel()
        time_of_cancelation = self.signup.signed_up_on
        self.assertEqual(self.time_selected, time_of_cancelation)
        self.assertEqual(self.signup.status, Signup.Status.Canceled)

        sleep(0.001)
        self.signup.resignup()
        self.assertLess(time_of_cancelation, self.signup.signed_up_on)
        self.assertEqual(self.signup.status, Signup.Status.Waiting)

    def test_update_is_certain_sets_to_waiting_list_and_removes_priority(self):
        self.assertEqual(self.signup.status, Signup.Status.Selected)
        self.assertTrue(self.signup.has_priority())

        self.signup.update_is_certain(False)
        time_of_update_to_uncertain = self.signup.signed_up_on
        self.assertLess(self.time_selected, time_of_update_to_uncertain)
        self.assertEqual(self.signup.status, Signup.Status.Waiting)
        self.assertFalse(self.signup.has_priority())

        sleep(0.001)
        self.signup.update_is_certain(True)
        self.assertEqual(time_of_update_to_uncertain, self.signup.signed_up_on)
        self.assertEqual(self.signup.status, Signup.Status.Waiting)
        self.assertTrue(self.signup.has_priority())

    def test_update_for_time_sets_to_waiting_list_and_removes_priority(self):
        self.assertEqual(self.signup.status, Signup.Status.Selected)
        self.assertTrue(self.signup.has_priority())

        self.signup.update_for_time(Signup.Time.ArriveLate)
        time_of_update_to_arrive_late = self.signup.signed_up_on
        self.assertLess(self.time_selected, time_of_update_to_arrive_late)
        self.assertEqual(self.signup.status, Signup.Status.Waiting)
        self.assertFalse(self.signup.has_priority())

        sleep(0.001)
        self.signup.update_for_time(Signup.Time.LeaveEarly)
        self.assertEqual(time_of_update_to_arrive_late, self.signup.signed_up_on)
        self.assertEqual(self.signup.status, Signup.Status.Waiting)
        self.assertFalse(self.signup.has_priority())

        sleep(0.001)
        self.signup.update_for_time(Signup.Time.Individually)
        self.assertEqual(time_of_update_to_arrive_late, self.signup.signed_up_on)
        self.assertEqual(self.signup.status, Signup.Status.Waiting)
        self.assertFalse(self.signup.has_priority())

        sleep(0.001)
        self.signup.update_for_time(Signup.Time.WholeDay)
        self.assertEqual(time_of_update_to_arrive_late, self.signup.signed_up_on)
        self.assertEqual(self.signup.status, Signup.Status.Waiting)
        self.assertTrue(self.signup.has_priority())

    def test_for_sketchy_weather_does_not_affect_status_and_priority(self):
        self.assertTrue(self.signup.for_sketchy_weather)
        self.assertEqual(self.signup.status, Signup.Status.Selected)
        self.assertTrue(self.signup.has_priority())

        self.signup.for_sketchy_weather = False
        self.assertEqual(self.signup.status, Signup.Status.Selected)
        self.assertTrue(self.signup.has_priority())


class TrainingCreateViewTests(TestCase):
    def setUp(self):
        self.pilot = User.objects.create(username="Pilot")
        self.client.force_login(self.pilot)

    @mock.patch("trainings.forms.datetime.date", wraps=date)
    def test_prefilled_default_is_next_august(self, mocked_date):
        mocked_date.today.return_value = date(1984, 1, 1)
        with self.assertNumQueries(2):
            response = self.client.get(reverse("create_trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/create_trainings.html")
        self.assertContains(response, 'value="1984-08-01"')
        self.assertContains(response, 'value="1984-08-31"')
        self.assertContains(response, 'value="1984-04-15"')
        self.assertContains(response, 'value="Axalpwochen"')
        self.assertContains(response, 'name="max_pilots" value=10')

        mocked_date.today.return_value = date(1984, 8, 1)
        with self.assertNumQueries(2):
            response = self.client.get(reverse("create_trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/create_trainings.html")
        self.assertContains(response, 'value="1985-08-01"')

    def test_create_trainings(self):
        with self.assertNumQueries(14):
            response = self.client.post(
                reverse("create_trainings"),
                data={
                    "first_day": TOMORROW,
                    "last_day": TOMORROW + timedelta(days=3),
                    "info": "Info",
                    "max_pilots": 11,
                    "priority_date": TODAY,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertEqual(4, len(Training.objects.all()))

    def test_creating_training_does_not_delete_signups(self):
        training = Training.objects.create(date=TODAY, info="Old info")
        signup = Signup.objects.create(pilot=self.pilot, training=training)
        training.select_signups()
        signup.refresh_from_db()
        self.assertEqual(signup.status, Signup.Status.Selected)

        with self.assertNumQueries(10):
            response = self.client.post(
                reverse("create_trainings"),
                data={
                    "first_day": TODAY,
                    "last_day": TODAY,
                    "info": "New info",
                    "max_pilots": 10,
                    "priority_date": TODAY,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        training.refresh_from_db()
        self.assertEqual(training.info, "New info")
        signup.refresh_from_db()
        self.assertEqual(signup.status, Signup.Status.Selected)

    def test_cannot_create_trainings_in_the_past(self):
        with self.assertNumQueries(2):
            response = self.client.post(
                reverse("create_trainings"),
                data={
                    "first_day": YESTERDAY,
                    "last_day": TOMORROW,
                    "info": "Info",
                    "max_pilots": 11,
                    "priority_date": TODAY,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/create_trainings.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Training.objects.all()))

    def test_cannot_create_trainings_more_than_a_year_ahead(self):
        with self.assertNumQueries(2):
            response = self.client.post(
                reverse("create_trainings"),
                data={
                    "first_day": TODAY + timedelta(days=666),
                    "last_day": TODAY + timedelta(days=1337),
                    "info": "Info",
                    "max_pilots": 11,
                    "priority_date": TODAY,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/create_trainings.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Training.objects.all()))

    def test_cannot_create_more_than_31_trainings(self):
        with self.assertNumQueries(2):
            response = self.client.post(
                reverse("create_trainings"),
                data={
                    "first_day": TODAY,
                    "last_day": TODAY + timedelta(days=32),
                    "info": "Info",
                    "max_pilots": 11,
                    "priority_date": TODAY,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/create_trainings.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Training.objects.all()))

    def test_last_day_must_be_after_first_day(self):
        with self.assertNumQueries(2):
            response = self.client.post(
                reverse("create_trainings"),
                data={
                    "first_day": TOMORROW,
                    "last_day": YESTERDAY,
                    "info": "Info",
                    "max_pilots": 11,
                    "priority_date": TODAY,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/create_trainings.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Training.objects.all()))

    def test_max_pilots_range(self):
        with self.assertNumQueries(2):
            response = self.client.post(
                reverse("create_trainings"),
                data={"max_pilots": 5},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/create_trainings.html")
        self.assertContains(response, "alert-warning")

        with self.assertNumQueries(2):
            response = self.client.post(
                reverse("create_trainings"),
                data={"max_pilots": 22},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/create_trainings.html")
        self.assertContains(response, "alert-warning")
    
    def test_cannot_create_trainings_for_non_existent_date(self):
        with self.assertNumQueries(2):
            response = self.client.post(
                reverse("create_trainings"),
                data={"first_day": "2022-13-13"},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/create_trainings.html")
        self.assertContains(response, "alert-warning")


class TrainingListViewTests(TestCase):
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
    
    def test_page_and_training_are_in_next_urls_of_update_buttons(self):
        for i in range(3, 10):
            training = Training.objects.create(date=TOMORROW + timedelta(days=i))
            Signup(pilot=self.pilot_a, training=training).save()
        
        with self.assertNumQueries(14):
            response = self.client.get(reverse("trainings") + "?page=2")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "trainings/&page=2&training=1")
        self.assertContains(response, "ansagen/?page=2&training=1")


class TrainingUpdateViewTests(TestCase):
    def setUp(self):
        self.pilot = User.objects.create(username="Pilot")
        self.client.force_login(self.pilot)
        self.training = Training.objects.create(date=TODAY)

        self.default_info = "Training findet statt"
        self.new_info = "Training abgesagt"

    def test_form_is_prefilled(self):
        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("update_training", kwargs={"date": TODAY})
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_training.html")
        self.assertContains(response, self.training.max_pilots)
        self.assertContains(response, self.training.priority_date.isoformat())
        self.assertContains(response, self.default_info)

    def test_update_training(self):
        with self.assertNumQueries(4):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotContains(response, self.default_info)
        self.assertNotContains(response, self.new_info)

        new_max_pilots = self.training.max_pilots - 1
        new_priority_date = self.training.priority_date - timedelta(days=1)
        with self.assertNumQueries(4 + 4):
            response = self.client.post(
                reverse("update_training", kwargs={"date": TODAY}),
                data={
                    "info": self.new_info,
                    "max_pilots": new_max_pilots,
                    "priority_date": new_priority_date,
                },
                follow=True,
            )
        self.training.refresh_from_db()
        self.assertEqual(self.training.info, self.new_info)
        self.assertEqual(self.training.max_pilots, new_max_pilots)
        self.assertEqual(self.training.priority_date, new_priority_date)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotContains(response, self.default_info)
        self.assertContains(response, self.new_info)

    def test_max_pilots_range(self):
        with self.assertNumQueries(3):
            response = self.client.post(
                reverse("update_training", kwargs={"date": TODAY}),
                data={"info": self.new_info, "max_pilots": 5},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_training.html")
        self.assertContains(response, self.new_info)
        self.assertContains(response, "alert-warning")

        with self.assertNumQueries(3):
            response = self.client.post(
                reverse("update_training", kwargs={"date": TODAY}),
                data={"info": self.new_info, "max_pilots": 22},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_training.html")
        self.assertContains(response, self.new_info)
        self.assertContains(response, "alert-warning")

    def test_cannot_update_past_or_non_existing_trainings_404(self):
        Training(date=YESTERDAY).save()
        with self.assertNumQueries(2):
            response = self.client.get(
                reverse("update_training", kwargs={"date": YESTERDAY}),
            )
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")

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

    def test_next_urls(self):
        response = self.client.get(
            reverse("update_training", kwargs={"date": TODAY})
            + f"?next={reverse('trainings')}&page=2&training=3",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_training.html")
        self.assertContains(response, reverse("trainings") + "?page=2#training_3")


class EmergencyMailViewTests(TestCase):
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

    def test_cannot_send_emergency_mail_for_past_or_non_existing_trainings_404(self):
        with self.assertNumQueries(2):
            response = self.client.post(
                reverse("emergency_mail", kwargs={"date": YESTERDAY}),
                data={"start": "2", "end": "5", "emergency_contacts": ["4", "5"]},
                follow=True,
            )
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")

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

    def test_cannot_send_emergency_mail_for_trainings_far_ahead_404(self):
        with self.assertNumQueries(2):
            response = self.client.post(
                reverse("emergency_mail", kwargs={"date": self.in_a_week}),
                data={"start": "2", "end": "5", "emergency_contacts": ["6", "7"]},
                follow=True,
            )
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")


class SingupListViewTests(TestCase):
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


class SignupCreateViewTests(TestCase):
    def setUp(self):
        self.pilot = User.objects.create(username="Pilot")
        self.client.force_login(self.pilot)

        self.monday = date(2007, 1, 1)
        self.assertEqual(self.monday.strftime("%A"), "Montag")
        self.wednesday = date(2007, 1, 3)
        self.assertEqual(self.wednesday.strftime("%A"), "Mittwoch")
        self.saturday = date(2007, 1, 6)
        self.assertEqual(self.saturday.strftime("%A"), "Samstag")
        self.sunday = date(2007, 1, 7)
        self.assertEqual(self.sunday.strftime("%A"), "Sonntag")
        self.next_saturday = date(2007, 1, 13)
        self.assertEqual(self.next_saturday.strftime("%A"), "Samstag")

    @mock.patch("trainings.views.datetime.date")
    @mock.patch("trainings.views.reverse_lazy")
    def test_default_date_is_next_saturday(self, mocked_reverse, mocked_date):
        mocked_reverse.return_value = ""
        mocked_date.today.return_value = self.monday
        with self.assertNumQueries(2):
            response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, self.saturday.isoformat())

        mocked_date.today.return_value = self.saturday
        with self.assertNumQueries(2):
            response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, self.saturday.isoformat())

        mocked_date.today.return_value = self.sunday
        with self.assertNumQueries(2):
            response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, self.next_saturday.isoformat())

    @mock.patch("trainings.forms.datetime", wraps=datetime)
    def test_default_priority_date_is_wednesday_before_training(self, mocked_date):
        mocked_date.date.today.return_value = self.monday
        dates = [self.wednesday, self.saturday, self.sunday, self.next_saturday]
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
            self.assertEqual(training.priority_date.strftime("%A"), "Mittwoch")
            self.assertLess(training.priority_date, training.date)
            self.assertLessEqual(
                training.date - training.priority_date, timedelta(days=7)
            )

    def test_cannot_signup_twice(self):
        with self.assertNumQueries(6):
            self.client.post(
                reverse("signup"),
                data={"date": TODAY, "for_time": Signup.Time.WholeDay},
            )
        self.assertEqual(1, len(Signup.objects.all()))

        with self.assertNumQueries(5):
            response = self.client.post(
                reverse("signup"),
                data={"date": TODAY, "for_time": Signup.Time.WholeDay},
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

    def test_cannot_signup_for_non_existent_date_404(self):
        with self.assertNumQueries(2):
            response = self.client.get(
                reverse("signup", kwargs={"date": "2022-13-13"}),
            )
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")

    def test_next_urls(self):
        response = self.client.get(
            reverse("signup", kwargs={"date": TODAY})
            + f"?page=2&training=3",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, reverse("trainings") + "?page=2#training_3")

        with self.assertNumQueries(8):
            response = self.client.post(
                reverse("signup"),
                data={"date": TODAY, "for_time": Signup.Time.WholeDay},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/signup.html")
        self.assertContains(response, TOMORROW.isoformat())
        self.assertEqual(1, len(Signup.objects.all()))


class SignupUpdateViewTests(TestCase):
    def setUp(self):
        self.pilot = User.objects.create(username="Pilot")
        self.client.force_login(self.pilot)
        training = Training.objects.create(date=TODAY)
        self.signup = Signup.objects.create(
            pilot=self.pilot, training=training, comment="Test comment"
        )

    def test_day_is_displayed(self):
        with self.assertNumQueries(5):
            response = self.client.get(reverse("update_signup", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, TODAY.strftime("%A, %d. %B").replace(" 0", " "))

    def test_comment_is_in_form_and_can_be_updated(self):
        with self.assertNumQueries(5):
            response = self.client.get(reverse("update_signup", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, 'value="Test comment"')

        with self.assertNumQueries(11):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY}),
                data={"for_time": self.signup.for_time, "comment": "Updated comment"},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.signup.refresh_from_db()
        self.assertContains(response, "Updated comment")
        self.assertEqual(self.signup.comment, "Updated comment")

    def test_cancel_and_resignup_from_trainings_list(self):
        with self.assertNumQueries(6):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "100%")
        self.assertContains(response, "Ganzer Tag")
        self.assertContains(response, "bi-cloud-haze2-fill")
        self.assertContains(response, "Test comment")

        with self.assertNumQueries(4 + 1 + 5):
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
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "bi-x-octagon")
        self.assertNotContains(response, "%")
        self.assertNotContains(response, "Ganzer Tag")
        self.assertNotContains(response, "bi-cloud-haze2-fill")
        self.assertContains(response, "Test comment")

        with self.assertNumQueries(4 + 1 + 5 + 1):
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
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "bi-cloud-check")
        self.assertTrue(self.signup.is_certain)
        self.assertContains(response, "100%")
        self.assertContains(response, "bi-cloud-haze2-fill")
        self.assertContains(response, "Test comment")

    def test_cancel_and_resignup_from_signups_list(self):
        with self.assertNumQueries(4 + 1 + 5):
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
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_signups.html")
        self.assertContains(response, "bi-x-octagon")

        with self.assertNumQueries(4 + 1 + 5 + 1):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY})
                + "?next="
                + reverse("my_signups"),
                data={"resignup": "", "for_time": self.signup.for_time},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_signups.html")
        self.assertContains(response, "bi-cloud-check")

    def test_update_is_certain(self):
        with self.assertNumQueries(6):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "100%")

        with self.assertNumQueries(5):
            response = self.client.get(reverse("update_signup", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, 'name="is_certain"')

        with self.assertNumQueries(11):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY}),
                data={"is_certain": False, "for_time": self.signup.for_time},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "75%")

    def test_update_for_time(self):
        with self.assertNumQueries(6):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "Ganzer Tag")

        with self.assertNumQueries(5):
            response = self.client.get(reverse("update_signup", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, 'name="for_time"')

        with self.assertNumQueries(11):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY}),
                data={
                    "is_certain": self.signup.is_certain,
                    "for_time": Signup.Time.ArriveLate,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "Kommt später")

    def test_update_for_sketchy_weather(self):
        with self.assertNumQueries(6):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "bi-cloud-haze2-fill")
        self.assertNotContains(response, "bi-sun")

        with self.assertNumQueries(5):
            response = self.client.get(reverse("update_signup", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, 'name="for_sketchy_weather"')

        with self.assertNumQueries(10):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": TODAY}),
                data={
                    "is_certain": self.signup.is_certain,
                    "for_sketchy_weather": "False",
                    "for_time": self.signup.for_time,
                },
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotContains(response, "bi-cloud-haze2-fill")
        self.assertContains(response, "bi-sun")

    def test_next_urls(self):
        response = self.client.get(
            reverse("update_signup", kwargs={"date": TODAY})
            + f"?next={reverse('trainings')}&page=2&training=3",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/update_signup.html")
        self.assertContains(response, reverse("trainings") + "?page=2#training_3")

        response = self.client.post(
            reverse("update_signup", kwargs={"date": TODAY})
            + "?next=http://danger.com",
            data={"for_time": Signup.Time.WholeDay},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")

    def test_cannot_update_past_or_non_existent_signup_404(self):
        training = Training.objects.create(date=YESTERDAY)
        Signup(pilot=self.pilot, training=training).save()
        with self.assertNumQueries(2):
            response = self.client.post(
                reverse("update_signup", kwargs={"date": YESTERDAY}),
                data={"for_time": self.signup.for_time, "comment": "Updated comment"},
                follow=True,
            )
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")

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

from datetime import date, timedelta
import locale
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .models import Training, Signup

locale.setlocale(locale.LC_TIME, "de_CH")

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


class TrainingListViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            email="orga@example.com", role=get_user_model().Role.Orga
        )
        self.pilot_b = get_user_model().objects.create(email="pilot_b@example.com")
        self.client.force_login(self.orga)

        Training(date=YESTERDAY).save()
        self.todays_training = Training.objects.create(date=TODAY)
        tomorrows_training = Training.objects.create(date=TOMORROW)
        Training.objects.create(date=TOMORROW + timedelta(days=1))
        Training.objects.create(date=TOMORROW + timedelta(days=2))

        self.signup = Signup.objects.create(
            pilot=self.orga, training=self.todays_training
        )
        Signup(pilot=self.pilot_b, training=tomorrows_training).save()

    def test_past_trainings_not_listed(self):
        with self.assertNumQueries(7):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotContains(
            response, YESTERDAY.strftime("%A, %d. %B").replace(" 0", " ")
        )
        self.assertContains(response, TODAY.strftime("%A, %d. %B").replace(" 0", " "))
        self.assertContains(
            response, TOMORROW.strftime("%A, %d. %B").replace(" 0", " ")
        )

    def test_showing_either_signup_or_update_button(self):
        with self.assertNumQueries(7):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, reverse("update_signup", kwargs={"date": TODAY}))
        self.assertNotContains(response, reverse("signup", kwargs={"date": TODAY}))
        self.assertContains(response, reverse("signup", kwargs={"date": TOMORROW}))

        self.client.force_login(self.pilot_b)
        with self.assertNumQueries(5):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
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
        self.todays_training.emergency_mail_sender = self.orga
        self.todays_training.save()
        with self.assertNumQueries(6):
            response = self.client.get(reverse("trainings"))
        self.assertContains(response, "disabled")

    def test_page_and_training_are_in_next_urls_of_update_buttons(self):
        for i in range(3, 10):
            training = Training.objects.create(date=TOMORROW + timedelta(days=i))
            Signup(pilot=self.orga, training=training).save()

        with self.assertNumQueries(14):
            response = self.client.get(reverse("trainings") + "?page=2")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, "trainings/&page=2&training=1")
        self.assertContains(response, "ansagen/?page=2&training=1")


class TrainingCreateViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            email="orga@example.com", role=get_user_model().Role.Orga
        )
        self.client.force_login(self.orga)

    def test_orga_required(self):
        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        with self.assertNumQueries(2):
            response = self.client.get(reverse("create_trainings"))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "403.html")

    def test_only_orga_sees_menu_entry(self):
        with self.assertNumQueries(3):
            response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, reverse("create_trainings"))

        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        with self.assertNumQueries(3):
            response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "base.html")
        self.assertNotContains(response, reverse("create_trainings"))

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
        signup = Signup.objects.create(pilot=self.orga, training=training)
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


class TrainingUpdateViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            email="orga@example.com", role=get_user_model().Role.Orga
        )
        self.client.force_login(self.orga)
        self.training = Training.objects.create(date=TODAY)

        self.default_info = "Training findet statt"
        self.new_info = "Training abgesagt"

    def test_orga_required(self):
        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        with self.assertNumQueries(2):
            response = self.client.get(
                reverse("update_training", kwargs={"date": TODAY})
            )
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "403.html")

    def test_only_orga_sees_button(self):
        with self.assertNumQueries(4):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(
            response, reverse("update_training", kwargs={"date": TODAY})
        )

        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        with self.assertNumQueries(4):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotContains(
            response, reverse("update_training", kwargs={"date": TODAY})
        )

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
        self.orga = get_user_model().objects.create(
            email="sender@example.com",
            first_name="Name A",
            role=get_user_model().Role.Orga,
        )
        self.client.force_login(self.orga)
        self.pilot_b = get_user_model().objects.create(
            email="pilot_b@example.com", first_name="Name B"
        )
        self.pilot_c = get_user_model().objects.create(
            email="pilot_c@example.com", first_name="Name C"
        )

        self.todays_training = Training.objects.create(date=TODAY)
        self.signup_a_today = Signup.objects.create(
            pilot=self.orga, training=self.todays_training
        )
        Signup(pilot=self.pilot_b, training=self.todays_training).save()
        Signup(pilot=self.pilot_c, training=self.todays_training).save()
        self.todays_training.select_signups()

        yesterdays_training = Training.objects.create(date=YESTERDAY)
        Signup.objects.create(pilot=self.orga, training=yesterdays_training).save()
        Signup.objects.create(pilot=self.pilot_b, training=yesterdays_training).save()
        yesterdays_training.select_signups()

        self.in_a_week = TODAY + timedelta(days=7)
        training_in_a_week = Training.objects.create(date=self.in_a_week)
        Signup(pilot=self.orga, training=training_in_a_week).save()
        Signup(pilot=self.pilot_b, training=training_in_a_week).save()
        training_in_a_week.select_signups()

    def test_orga_required(self):
        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        with self.assertNumQueries(2):
            response = self.client.get(
                reverse("emergency_mail", kwargs={"date": TODAY})
            )
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "403.html")

    def test_only_orga_sees_button(self):
        with self.assertNumQueries(5):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertContains(response, reverse("emergency_mail", kwargs={"date": TODAY}))

        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        with self.assertNumQueries(5):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")
        self.assertNotContains(
            response, reverse("emergency_mail", kwargs={"date": TODAY})
        )

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
        self.assertTrue(self.orga.email in mail.outbox[0].to)
        self.assertTrue("8:30 bis 20:00" in mail.outbox[0].body)
        self.assertTrue(self.orga.first_name in mail.outbox[0].body)
        self.assertTrue(self.pilot_b.first_name in mail.outbox[0].body)
        self.assertTrue(self.pilot_c.first_name not in mail.outbox[0].body)

        self.todays_training.refresh_from_db()
        self.assertTrue(self.todays_training.emergency_mail_sender == self.orga)

    def test_only_selected_signups_can_be_chosen(self):
        with self.assertNumQueries(5):
            response = self.client.get(
                reverse("emergency_mail", kwargs={"date": TODAY})
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(response, self.orga.first_name)
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
        self.assertNotContains(response, self.orga.first_name)
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

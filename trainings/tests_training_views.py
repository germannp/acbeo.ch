from datetime import date, timedelta
from http import HTTPStatus
import locale
from random import randint
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Training, Signup


locale.setlocale(locale.LC_TIME, "de_CH")

TODAY = timezone.now().date()
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)


class TrainingListViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            email="orga@example.com", role=get_user_model().Role.ORGA
        )
        self.pilot_b = get_user_model().objects.create(email="pilot_b@example.com")
        self.client.force_login(self.orga)

        Training(date=YESTERDAY).save()
        self.todays_training = Training.objects.create(date=TODAY)
        self.tomorrows_training = Training.objects.create(date=TOMORROW)
        Training(date=TOMORROW + timedelta(days=1)).save()
        self.last_training = Training.objects.create(
            date=TOMORROW + timedelta(days=2), priority_date=TOMORROW
        )

        self.signup = Signup.objects.create(
            pilot=self.orga, training=self.todays_training
        )
        Signup(pilot=self.pilot_b, training=self.tomorrows_training).save()

    def test_signup_button_when_no_trainings_listed(self):
        Training.objects.all().exclude(date=TODAY).delete()
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertNotContains(response, "btn-secondary")

        self.todays_training.delete()
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertContains(response, "btn-secondary")

    def test_list_trainings_selects_signups(self):
        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, Signup.Status.WAITING)

        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")

        self.signup.refresh_from_db()
        self.assertEqual(self.signup.status, Signup.Status.SELECTED)

    def test_freshly_selected_signups_are_listed_first(self):
        now = timezone.now()
        low_priority_signup = Signup.objects.create(
            pilot=self.pilot_b,
            training=self.last_training,
            signed_up_on=now,
            is_certain=False,
        )
        now += timedelta(hours=1)
        normal_signup = Signup.objects.create(
            pilot=self.orga, training=self.last_training, signed_up_on=now
        )
        for signup in [low_priority_signup, normal_signup]:
            signup.refresh_from_db()
            self.assertEqual(signup.status, Signup.Status.WAITING)

        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        table = str(response.content).split('<div class="card mb-4"')[-1]
        self.assertTrue("bi-cloud-check" not in table.split("bi-hourglass-split")[-1])

        for signup in [low_priority_signup, normal_signup]:
            signup.refresh_from_db()
        self.assertEqual(low_priority_signup.status, Signup.Status.WAITING)
        self.assertEqual(normal_signup.status, Signup.Status.SELECTED)

    def test_past_trainings_not_listed(self):
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertNotContains(
            response, YESTERDAY.strftime("%A, %d. %b").replace(" 0", " ")
        )
        self.assertContains(response, TODAY.strftime("%A, %d. %b").replace(" 0", " "))
        self.assertContains(
            response, TOMORROW.strftime("%A, %d. %b").replace(" 0", " ")
        )

    def test_showing_either_signup_or_update_button(self):
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertContains(response, reverse("update_signup", kwargs={"date": TODAY}))
        self.assertNotContains(response, reverse("signup", kwargs={"date": TODAY}))
        self.assertContains(response, reverse("signup", kwargs={"date": TOMORROW}))

        self.client.force_login(self.pilot_b)
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertContains(response, reverse("signup", kwargs={"date": TODAY}))
        self.assertContains(
            response, reverse("update_signup", kwargs={"date": TOMORROW})
        )
        self.assertNotContains(response, reverse("signup", kwargs={"date": TOMORROW}))

    def test_text_color(self):
        for i, (is_certain, duration, warning) in enumerate(
            [
                (True, Signup.Duration.ALL_DAY, False),
                (False, Signup.Duration.ALL_DAY, True),
                (True, Signup.Duration.ARRIVING_LATE, True),
                (True, Signup.Duration.LEAVING_EARLY, True),
                (True, Signup.Duration.INDIVIDUALLY, True),
            ]
        ):
            with self.subTest(
                is_certain=is_certain, duration=duration, warning=warning
            ):
                self.signup.is_certain = is_certain
                self.signup.duration = duration
                self.signup.save()
                response = self.client.get(reverse("trainings"))
                self.assertEqual(response.status_code, HTTPStatus.OK)
                self.assertTemplateUsed(response, "trainings/training_list.html")
                self.assertNotContains(response, "bi-hourglass-split")
                if warning:
                    self.assertContains(response, "text-warning")
                else:
                    self.assertNotContains(response, "text-warning")

        for status, muted in [
            (Signup.Status.SELECTED, False),
            (Signup.Status.CANCELED, True),
        ]:
            with self.subTest(status=status, muted=muted):
                self.signup.status = status
                self.signup.save()
                response = self.client.get(reverse("trainings"))
                self.assertEqual(response.status_code, HTTPStatus.OK)
                self.assertTemplateUsed(response, "trainings/training_list.html")
                self.assertNotContains(response, "bi-hourglass-split")
                if muted:
                    self.assertContains(response, "text-muted")
                else:
                    self.assertNotContains(response, "text-muted")

    def test_update_info_button(self):
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        for i in range(4):
            date = TODAY + timedelta(days=i)
            self.assertContains(
                response,
                reverse("update_training", kwargs={"date": date}),
            )

    def test_page_and_training_are_in_next_urls_of_update_buttons(self):
        for i in range(3, 10):
            training = Training.objects.create(date=TOMORROW + timedelta(days=i))
            Signup(pilot=self.orga, training=training).save()

        response = self.client.get(reverse("trainings") + "?page=2")
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertContains(response, "trainings/&page=2&training=1")
        self.assertContains(response, "ansagen/?page=2&training=1")

    def test_emergency_mail_button(self):
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        for i in range(3):
            date = TODAY + timedelta(days=i)
            self.assertContains(
                response,
                reverse("emergency_mail", kwargs={"date": date}),
            )
        date = TODAY + timedelta(days=3)
        self.assertNotContains(
            response, reverse("emergency_mail", kwargs={"date": date})
        )
        self.assertNotContains(response, "text-muted")

        self.todays_training.emergency_mail_sender = self.orga
        self.todays_training.save()
        response = self.client.get(reverse("trainings"))
        self.assertContains(response, "text-muted")

    def test_report_button(self):
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertEqual(2, str(response.content).count(reverse("create_report")))


class TrainingCreateViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            email="orga@example.com", role=get_user_model().Role.ORGA
        )
        self.staff = get_user_model().objects.create(
            email="staff@example.com", role=get_user_model().Role.STAFF
        )
        self.client.force_login(self.staff)

    def test_staff_required(self):
        self.client.force_login(self.orga)
        response = self.client.get(reverse("create_trainings"))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_only_staff_sees_menu_entry(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, reverse("create_trainings"))

        self.client.force_login(self.orga)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "base.html")
        self.assertNotContains(response, reverse("create_trainings"))

    @mock.patch("trainings.forms.timezone", wraps=timezone)
    def test_prefilled_default_is_next_august(self, mocked_timezone):
        mocked_now = mock.MagicMock()
        mocked_now.date.return_value = date(1984, 1, 1)
        mocked_timezone.now.return_value = mocked_now
        response = self.client.get(reverse("create_trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_create.html")
        self.assertContains(response, 'value="1984-08-01"')
        self.assertContains(response, 'value="1984-08-31"')
        self.assertContains(response, 'value="1984-04-15"')
        self.assertContains(response, 'value="Axalpwochen"')
        self.assertContains(response, 'name="max_pilots" value=10')

        mocked_now.date.return_value = date(1984, 8, 1)
        response = self.client.get(reverse("create_trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_create.html")
        self.assertContains(response, 'value="1985-08-01"')

    def test_create_trainings(self):
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
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertEqual(4, len(Training.objects.all()))

    def test_creating_training_does_not_delete_signups(self):
        training = Training.objects.create(date=TODAY, info="Old info")
        signup = Signup.objects.create(pilot=self.orga, training=training)
        training.select_signups()
        signup.refresh_from_db()
        self.assertEqual(signup.status, Signup.Status.SELECTED)

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
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        training.refresh_from_db()
        self.assertEqual(training.info, "New info")
        signup.refresh_from_db()
        self.assertEqual(signup.status, Signup.Status.SELECTED)

    def test_cannot_create_trainings_in_the_past(self):
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
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_create.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Training.objects.all()))

    def test_cannot_create_trainings_more_than_a_year_ahead(self):
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
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_create.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Training.objects.all()))

    def test_cannot_create_more_than_31_trainings(self):
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
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_create.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Training.objects.all()))

    def test_last_day_must_be_after_first_day(self):
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
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_create.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Training.objects.all()))

    def test_priority_date_cannot_be_after_last_day(self):
        response = self.client.post(
            reverse("create_trainings"),
            data={
                "first_day": TODAY,
                "last_day": TOMORROW,
                "info": "Info",
                "max_pilots": 11,
                "priority_date": TOMORROW + timedelta(days=1),
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_create.html")
        self.assertContains(response, "alert-warning")
        self.assertEqual(0, len(Training.objects.all()))

    def test_max_pilots_range(self):
        response = self.client.post(
            reverse("create_trainings"),
            data={"max_pilots": 5},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_create.html")
        self.assertContains(response, "alert-warning")

        response = self.client.post(
            reverse("create_trainings"),
            data={"max_pilots": 22},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_create.html")
        self.assertContains(response, "alert-warning")

    def test_cannot_create_trainings_for_non_existent_date(self):
        response = self.client.post(
            reverse("create_trainings"),
            data={"first_day": "2022-13-13"},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_create.html")
        self.assertContains(response, "alert-warning")


class TrainingUpdateViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            email="orga@example.com", role=get_user_model().Role.ORGA
        )
        self.client.force_login(self.orga)
        self.training = Training.objects.create(date=TODAY)

    def test_orga_required_to_see(self):
        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        response = self.client.get(reverse("update_training", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_only_orga_sees_button(self):
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertContains(
            response, reverse("update_training", kwargs={"date": TODAY})
        )

        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertNotContains(
            response, reverse("update_training", kwargs={"date": TODAY})
        )

    def test_form_is_prefilled(self):
        self.training.info = "Stored Info"
        self.training.save()
        response = self.client.get(reverse("update_training", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_update.html")
        self.assertContains(response, "Stored Info")
        self.assertContains(response, self.training.max_pilots)
        self.assertContains(response, self.training.priority_date.isoformat())

    def test_update_training(self):
        first_info = "Default Info"
        new_info = "New Info"

        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertNotContains(response, first_info)
        self.assertNotContains(response, new_info)

        new_max_pilots = self.training.max_pilots - 1
        new_priority_date = self.training.priority_date - timedelta(days=1)
        response = self.client.post(
            reverse("update_training", kwargs={"date": TODAY}),
            data={
                "info": new_info,
                "max_pilots": new_max_pilots,
                "priority_date": new_priority_date,
            },
            follow=True,
        )
        self.training.refresh_from_db()
        self.assertEqual(self.training.info, new_info)
        self.assertEqual(self.training.max_pilots, new_max_pilots)
        self.assertEqual(self.training.priority_date, new_priority_date)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertNotContains(response, first_info)
        self.assertContains(response, new_info)

    def test_max_pilots_range(self):
        response = self.client.post(
            reverse("update_training", kwargs={"date": TODAY}),
            data={"max_pilots": 5},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_update.html")
        self.assertContains(response, "alert-warning")

        response = self.client.post(
            reverse("update_training", kwargs={"date": TODAY}),
            data={"max_pilots": 22},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_update.html")
        self.assertContains(response, "alert-warning")

    def test_priority_date_cannot_be_after_last_day(self):
        response = self.client.post(
            reverse("update_training", kwargs={"date": TODAY}),
            data={"priority_date": TOMORROW},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_update.html")
        self.assertContains(response, "alert-warning")

    def test_cannot_update_past_or_non_existing_trainings(self):
        Training(date=YESTERDAY).save()
        response = self.client.get(
            reverse("update_training", kwargs={"date": YESTERDAY})
        )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        response = self.client.get(
            reverse("update_training", kwargs={"date": "2022-13-13"})
        )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        response = self.client.get(
            reverse("update_training", kwargs={"date": TOMORROW})
        )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

    def test_next_urls(self):
        response = self.client.get(
            reverse("update_training", kwargs={"date": TODAY})
            + f"?next={reverse('trainings')}&page=2&training=3"
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_update.html")
        self.assertContains(response, reverse("trainings") + "?page=2#training_3")


class EmergencyMailViewTests(TestCase):
    def setUp(self):
        self.orga = get_user_model().objects.create(
            email="sender@example.com",
            first_name="Name A",
            role=get_user_model().Role.ORGA,
        )
        self.client.force_login(self.orga)
        self.pilot_b = get_user_model().objects.create(
            email="pilot_b@example.com", first_name="Name B"
        )
        self.pilot_c = get_user_model().objects.create(
            email="pilot_c@example.com", first_name="Name C"
        )

        self.tomorrows_training = Training.objects.create(date=TOMORROW)
        self.signup_a_tomorrow = Signup.objects.create(
            pilot=self.orga, training=self.tomorrows_training
        )
        Signup(pilot=self.pilot_b, training=self.tomorrows_training).save()
        Signup(pilot=self.pilot_c, training=self.tomorrows_training).save()

        yesterdays_training = Training.objects.create(date=YESTERDAY)
        Signup(pilot=self.orga, training=yesterdays_training).save()
        Signup(pilot=self.pilot_b, training=yesterdays_training).save()

        self.in_a_week = TODAY + timedelta(days=7)
        training_in_a_week = Training.objects.create(date=self.in_a_week)
        Signup(pilot=self.orga, training=training_in_a_week).save()
        Signup(pilot=self.pilot_b, training=training_in_a_week).save()

    def test_orga_required_to_see(self):
        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        response = self.client.get(reverse("emergency_mail", kwargs={"date": TOMORROW}))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")

    def test_only_orga_sees_button(self):
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertContains(
            response, reverse("emergency_mail", kwargs={"date": TOMORROW})
        )

        guest = get_user_model().objects.create(email="guest@example.com")
        self.client.force_login(guest)
        response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertNotContains(
            response, reverse("emergency_mail", kwargs={"date": TOMORROW})
        )

    def test_get_emergency_mail_selects_signups(self):
        self.signup_a_tomorrow.refresh_from_db()
        self.assertEqual(self.signup_a_tomorrow.status, Signup.Status.WAITING)

        response = self.client.get(reverse("emergency_mail", kwargs={"date": TOMORROW}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(response, "Name A , ")

        self.signup_a_tomorrow.refresh_from_db()
        self.assertEqual(self.signup_a_tomorrow.status, Signup.Status.SELECTED)

    def test_new_pilots_warning_shown(self):
        response = self.client.get(reverse("emergency_mail", kwargs={"date": TOMORROW}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(
            response, "Name A, Name B und Name C sind zum ersten Mal dabei."
        )

        Signup.objects.first().delete()
        response = self.client.get(reverse("emergency_mail", kwargs={"date": TOMORROW}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(response, "Name B und Name C sind zum ersten Mal dabei.")
        self.assertNotContains(response, "Name A,")

        Signup.objects.first().delete()
        response = self.client.get(reverse("emergency_mail", kwargs={"date": TOMORROW}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(response, "Name C ist zum ersten Mal dabei.")
        self.assertNotContains(response, "und Name C")

    def test_only_selected_signups_can_be_chosen(self):
        response = self.client.get(reverse("emergency_mail", kwargs={"date": TOMORROW}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(response, self.orga.first_name)
        self.assertContains(response, self.pilot_b.first_name)
        self.assertContains(response, self.pilot_c.first_name)

        self.signup_a_tomorrow.cancel()
        self.signup_a_tomorrow.save()
        response = self.client.get(reverse("emergency_mail", kwargs={"date": TOMORROW}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertNotContains(response, self.orga.first_name)
        self.assertContains(response, self.pilot_b.first_name)
        self.assertContains(response, self.pilot_c.first_name)

        response = self.client.post(
            reverse("emergency_mail", kwargs={"date": TOMORROW}),
            data={
                "start": "2",
                "end": "5",
                "emergency_contacts": ["1", "2"],
                "ctr_inactive": True,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(response, "Bitte eine gültige Auswahl treffen.")

    def test_exactly_two_emergency_contacts_must_be_selected(self):
        response = self.client.post(
            reverse("emergency_mail", kwargs={"date": TOMORROW}),
            data={
                "start": "2",
                "end": "5",
                "emergency_contacts": ["1"],
                "ctr_inactive": True,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(response, "Bitte genau zwei Notfallkontakte auswählen.")

        response = self.client.post(
            reverse("emergency_mail", kwargs={"date": TOMORROW}),
            data={
                "start": "2",
                "end": "5",
                "emergency_contacts": ["1", "2", "3"],
                "ctr_inactive": True,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(response, "Bitte genau zwei Notfallkontakte auswählen.")

    def test_ctr_must_be_inactive(self):
        response = self.client.post(
            reverse("emergency_mail", kwargs={"date": TOMORROW}),
            data={
                "start": "2",
                "end": "5",
                "emergency_contacts": ["1", "2"],
                "ctr_inactive": False,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(
            response,
            "Wir dürfen nur mit Absprache fliegen, wenn CTR/TMA Meiringen aktiv ist.",
        )

    def test_sending_emergency_mail(self):
        response = self.client.post(
            reverse("emergency_mail", kwargs={"date": TOMORROW}),
            data={
                "start": "2",
                "end": "5",
                "emergency_contacts": ["1", "2"],
                "ctr_inactive": True,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")
        self.assertContains(response, "Seepolizeimail abgesendet.")
        self.assertNotContains(
            response, "Name A, Name B und Name C sind zum ersten Mal dabei."
        )

        self.assertEqual(1, len(mail.outbox))
        self.assertTrue(
            TOMORROW.strftime("%A, %d. %B").replace(" 0", " ") in mail.outbox[0].subject
        )
        self.assertEqual(mail.outbox[0].from_email, "dev@example.com")
        self.assertEqual(
            mail.outbox[0].to,
            ["emergency@example.com", "emergency2@example.com", self.orga.email],
        )
        self.assertTrue("8:30 bis 20:00" in mail.outbox[0].body)
        self.assertTrue(self.orga.first_name in mail.outbox[0].body)
        self.assertTrue(self.pilot_b.first_name in mail.outbox[0].body)
        self.assertTrue(self.pilot_c.first_name not in mail.outbox[0].body)

        self.tomorrows_training.refresh_from_db()
        self.assertTrue(self.tomorrows_training.emergency_mail_sender == self.orga)

    def test_cannot_send_emergency_mail_twice(self):
        self.tomorrows_training.emergency_mail_sender = self.orga
        self.tomorrows_training.save()

        response = self.client.get(reverse("emergency_mail", kwargs={"date": TOMORROW}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")
        self.assertContains(
            response, f"{self.orga} hat bereits ein Seepolizeimail versandt."
        )
        self.assertContains(
            response, '<button class="btn btn-primary mt-3" type="submit" disabled>'
        )

        response = self.client.post(
            reverse("emergency_mail", kwargs={"date": TOMORROW}),
            data={
                "start": "2",
                "end": "5",
                "emergency_contacts": ["1", "2"],
                "ctr_inactive": True,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response, f"{self.orga} hat bereits ein Seepolizeimail versandt."
        )

    def test_cannot_send_emergency_mail_for_past_or_non_existing_trainings_404(self):
        response = self.client.post(
            reverse("emergency_mail", kwargs={"date": YESTERDAY}),
            data={
                "start": "2",
                "end": "5",
                "emergency_contacts": ["4", "5"],
                "ctr_inactive": True,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        response = self.client.get(
            reverse("emergency_mail", kwargs={"date": "2022-13-13"})
        )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

        response = self.client.get(reverse("emergency_mail", kwargs={"date": TODAY}))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")

    def test_next_urls(self):
        response = self.client.post(
            reverse("emergency_mail", kwargs={"date": TOMORROW})
            + f"?next={reverse('home')}",
            data={
                "start": "2",
                "end": "5",
                "emergency_contacts": ["1", "2"],
                "ctr_inactive": True,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/post_list.html")

    def test_cannot_send_emergency_mail_for_trainings_far_ahead_404(self):
        response = self.client.post(
            reverse("emergency_mail", kwargs={"date": self.in_a_week}),
            data={
                "start": "2",
                "end": "5",
                "emergency_contacts": ["6", "7"],
                "ctr_inactive": True,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")


class DatabaseCallsTests(TestCase):
    def setUp(self):
        self.num_pilots = randint(5, 10)
        self.num_days = randint(2, 6)

        staff = get_user_model().objects.create(
            email="staff@example.com",
            first_name="Staff",
            role=get_user_model().Role.STAFF,
        )
        self.client.force_login(staff)

        pilots = [staff] + [
            get_user_model().objects.create(
                email=f"pilot_{i}@example.com", first_name=f"Pilot {i}"
            )
            for i in range(self.num_pilots - 1)
        ]
        for i in range(self.num_days):
            training = Training.objects.create(date=TODAY + timedelta(days=i))
            for pilot in pilots:
                Signup(pilot=pilot, training=training).save()

    def test_training_list_view(self):
        with self.assertNumQueries(10 + self.num_days * self.num_pilots):
            response = self.client.get(reverse("trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_list.html")

    def test_training_create_view(self):
        with self.assertNumQueries(3):
            response = self.client.get(reverse("create_trainings"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_create.html")

        with self.assertNumQueries(2 + 2 * self.num_days):
            response = self.client.post(
                reverse("create_trainings"),
                data={
                    "first_day": TODAY + timedelta(days=90),
                    "last_day": TODAY + timedelta(days=90 + self.num_days - 1),
                    "info": "Info",
                    "max_pilots": 11,
                    "priority_date": TODAY,
                },
                follow=False,
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertEqual(2 * self.num_days, len(Training.objects.all()))

    def test_training_update_view(self):
        with self.assertNumQueries(4):
            response = self.client.get(
                reverse("update_training", kwargs={"date": TODAY})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/training_update.html")

        with self.assertNumQueries(4):
            response = self.client.post(
                reverse("update_training", kwargs={"date": TODAY}),
                data={
                    "info": "New Info",
                    "max_pilots": 11,
                    "priority_date": YESTERDAY,
                },
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

    def test_emergency_mail_view(self):
        with self.assertNumQueries(12 + self.num_pilots):
            response = self.client.get(
                reverse("emergency_mail", kwargs={"date": TODAY})
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/emergency_mail.html")

        with self.assertNumQueries(8):
            response = self.client.post(
                reverse("emergency_mail", kwargs={"date": TODAY}),
                data={
                    "start": "2",
                    "end": "5",
                    "emergency_contacts": ["1", "2"],
                    "ctr_inactive": True,
                },
            )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class UserCreationTests(TestCase):
    user_data = {
        "username": "John",
        "email": "test@mail.com",
        "first_name": "John",
        "last_name": "Doe",
        "password1": "qhTJ]?QZ.F}v5(nA",
        "password2": "qhTJ]?QZ.F}v5(nA",
    }

    def test_required_fields(self):
        for required_field in self.user_data.keys():
            partial_data = {
                key: value
                for key, value in self.user_data.items()
                if key != required_field
            }
            response = self.client.post(
                reverse("register"), data=partial_data, follow=True
            )
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, "news/register.html")
            self.assertEqual(0, len(User.objects.all()))
        response = self.client.post(
            reverse("register"), data=self.user_data, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/login.html")
        self.assertEqual(1, len(User.objects.all()))

    def test_username_and_email_must_be_unique(self):
        response = self.client.post(
            reverse("register"), data=self.user_data, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/login.html")
        self.assertEqual(1, len(User.objects.all()))

        response = self.client.post(
            reverse("register"), data=self.user_data, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/register.html")
        self.assertContains(response, "Ein Konto mit dieser Email existiert bereits.")
        self.assertContains(response, "Dieser Benutzername ist bereits vergeben.")
        self.assertEqual(1, len(User.objects.all()))

    def test_forwarding_after_registration_for_login_required(self):
        response = self.client.get(reverse("trainings"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/login.html")
        self.assertContains(response, "/register/?next=/trainings/")

        self.client.post(
            "/register/?next=/trainings/", data=self.user_data, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/login.html")
        self.assertContains(response, 'name="next" value="/trainings/"')

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse


class PostDetailTests(TestCase):
    def test_post_not_found_404(self):
        response = self.client.get(reverse("post", kwargs={"slug": "missing"}))
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")


class ContactFormTests(TestCase):
    email_data = {
        "email": "from@example.com",
        "subject": "Subject",
        "message": "Message",
    }

    def test_required_fields(self):
        for required_field in self.email_data.keys():
            partial_data = {
                key: value
                for key, value in self.email_data.items()
                if key != required_field
            }
            response = self.client.post(
                reverse("contact"), data=partial_data, follow=True
            )
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, "news/contact.html")
            self.assertEqual(0, len(mail.outbox))
        response = self.client.post(
            reverse("contact"), data=self.email_data, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/index.html")
        self.assertContains(response, "Nachricht abgesendet.")
        self.assertEqual(1, len(mail.outbox))
        self.assertEqual(mail.outbox[0].subject, self.email_data["subject"])
        self.assertEqual(mail.outbox[0].from_email, self.email_data["email"])
        self.assertEqual(mail.outbox[0].to, ["to@example.com"])
        self.assertEqual(mail.outbox[0].body, self.email_data["message"])


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

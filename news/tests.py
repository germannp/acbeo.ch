from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .models import Pilot


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
        self.assertEqual(mail.outbox[0].to, ["info@example.com"])
        self.assertEqual(mail.outbox[0].body, self.email_data["message"])


class PilotCreationTests(TestCase):
    pilot_data = {
        "email": "test@mail.com",
        "first_name": "John",
        "last_name": "Doe",
        "phone": "079 123 45 67",
        "password1": "qhTJ]?QZ.F}v5(nA",
        "password2": "qhTJ]?QZ.F}v5(nA",
        "accept_safety_concept": True,
    }

    def test_required_fields(self):
        for required_field in self.pilot_data.keys():
            partial_data = {
                key: value
                for key, value in self.pilot_data.items()
                if key != required_field
            }
            response = self.client.post(
                reverse("register"), data=partial_data, follow=True
            )
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, "news/register.html")
            self.assertEqual(0, len(Pilot.objects.all()))
        response = self.client.post(
            reverse("register"), data=self.pilot_data, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/login.html")
        self.assertEqual(1, len(Pilot.objects.all()))
    
    def test_safety_concept_must_be_accepted(self):
        partial_data = self.pilot_data.copy()
        partial_data["accept_safety_concept"] = False
        response = self.client.post(
            reverse("register"), data=partial_data, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/register.html")
        self.assertEqual(0, len(Pilot.objects.all()))

    def test_email_must_be_unique(self):
        response = self.client.post(
            reverse("register"), data=self.pilot_data, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/login.html")
        self.assertEqual(1, len(Pilot.objects.all()))

        response = self.client.post(
            reverse("register"), data=self.pilot_data, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/register.html")
        self.assertContains(response, "Pilot mit diesem Email existiert bereits.")
        self.assertEqual(1, len(Pilot.objects.all()))

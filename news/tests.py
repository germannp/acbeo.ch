from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .models import Pilot, Post


class PostListViewTests(TestCase):
    def setUp(self):
        author = Pilot.objects.create(email="author@example.com", first_name="Author")
        Post.objects.create(title="Test news", slug="test-news", author=author)

    def test_author_name_shown(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/index.html")
        self.assertContains(response, "Author")
        self.assertNotContains(response, "author@example.com")


class PostDetailViewTests(TestCase):
    def setUp(self):
        author = Pilot.objects.create(email="author@example.com", first_name="Author")
        Post.objects.create(title="Test news", slug="test-news", author=author)

    def test_author_name_shown(self):
        response = self.client.get(reverse("post", kwargs={"slug": "test-news"}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/post.html")
        self.assertContains(response, "Author")
        self.assertNotContains(response, "author@example.com")

    def test_post_not_found_404(self):
        response = self.client.get(reverse("post", kwargs={"slug": "missing"}))
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")


class ContactFormViewTests(TestCase):
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


class PilotCreationViewTests(TestCase):
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
        response = self.client.post(reverse("register"), data=partial_data, follow=True)
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


class MembershipFormViewTests(TestCase):
    def setUp(self):
        self.guest = Pilot.objects.create(
            email="guest@example.com", first_name="Guest", role=Pilot.Role.Guest
        )
        self.member = Pilot.objects.create(
            email="member@example.com", role=Pilot.Role.Member
        )
        self.client.force_login(self.guest)

    def test_statutes_must_be_accepted_and_comment_is_prefilled(self):
        response = self.client.post(
            reverse("membership"),
            data={"accept_statutes": False, "comment": "Kommentar"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/membership.html")
        self.assertContains(response, "Kommentar")
        self.assertContains(
            response, "Du musst mit unseren Statuten einverstanden sein."
        )
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.role, Pilot.Role.Guest)

    def test_becoming_member(self):
        response = self.client.post(
            reverse("membership"),
            data={"accept_statutes": True},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/index.html")
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.role, Pilot.Role.Member)

    def test_button_hidden_from_members(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/sidebar.html")
        self.assertContains(response, "Mitglied werden")

        self.client.force_login(self.member)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/sidebar.html")
        self.assertNotContains(response, "Mitglied werden")

    def test_form_forbidden_for_members(self):
        response = self.client.get(reverse("membership"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/membership.html")

        self.client.force_login(self.member)
        response = self.client.get(reverse("membership"))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "403.html")

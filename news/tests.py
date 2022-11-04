from http import HTTPStatus
from unittest import mock

from django.core import mail
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from .models import Pilot, Post
from .middleware import RedirectToNonWwwMiddleware


class RedirectToNonWwwMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.request_factory = RequestFactory()
        self.dummy_response = object()
        self.middleware = RedirectToNonWwwMiddleware(
            lambda request: self.dummy_response
        )

    def test_www_redirect(self):
        request = self.request_factory.get("/some-path/", HTTP_HOST="www.example.com")
        response = self.middleware(request)
        self.assertEqual(response.status_code, HTTPStatus.MOVED_PERMANENTLY)
        self.assertEqual(response["Location"], "https://example.com/some-path/")

    def test_non_redirect(self):
        request = self.request_factory.get("/some-path/", HTTP_HOST="example.com")
        response = self.middleware(request)
        self.assertIs(response, self.dummy_response)


class PostListViewTests(TestCase):
    def setUp(self):
        author = Pilot.objects.create(email="author@example.com", first_name="Author")
        Post(title="Test news", slug="test-news", author=author).save()

    def test_author_name_shown(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/index.html")
        self.assertContains(response, "Author")
        self.assertNotContains(response, "author@example.com")


class PostDetailViewTests(TestCase):
    def setUp(self):
        author = Pilot.objects.create(email="author@example.com", first_name="Author")
        Post(title="Test news", slug="test-news", author=author).save()

    def test_author_name_shown(self):
        response = self.client.get(reverse("post", kwargs={"slug": "test-news"}))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/post.html")
        self.assertContains(response, "Author")
        self.assertNotContains(response, "author@example.com")

    def test_post_not_found_404(self):
        response = self.client.get(reverse("post", kwargs={"slug": "missing"}))
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, "404.html")


class ContactFormViewTests(TestCase):
    def setUp(self):
        self.pilot = Pilot.objects.create(email="pilot@example.com")
        self.client.force_login(self.pilot)
        self.email_data = {
            "email": "from@example.com",
            "subject": "Subject",
            "message": "Message",
        }

    def test_required_fields_and_form_is_prefilled(self):
        for required_field in self.email_data.keys():
            partial_data = {
                key: value
                for key, value in self.email_data.items()
                if key != required_field
            }
            response = self.client.post(
                reverse("contact"), data=partial_data, follow=True
            )
            self.assertEqual(response.status_code, HTTPStatus.OK)
            self.assertTemplateUsed(response, "news/contact.html")
            for value in partial_data.values():
                self.assertContains(response, value)
            self.assertEqual(0, len(mail.outbox))

    def test_pilot_email_prefilled(self):
        response = self.client.get(reverse("contact"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/contact.html")
        self.assertContains(response, self.pilot.email)

    def test_subject_from_url(self):
        subject = "Some subject"
        response = self.client.get(reverse("contact") + f"?subject={subject}")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "news/contact.html")
        self.assertContains(response, subject)

    @mock.patch(
        "news.views.recaptcha.RecaptchaEnterpriseServiceClient.from_service_account_info"
    )
    def test_contact(self, MockedClient):
        mocked_response = mock.MagicMock(risk_analysis=mock.MagicMock(score=1337))
        mocked_client = mock.MagicMock()
        mocked_client.create_assessment.return_value = mocked_response
        MockedClient.return_value = mocked_client

        with self.assertLogs("spam-protection", level="INFO") as cm:
            response = self.client.post(
                reverse("contact"), data=self.email_data, follow=True
            )
            self.assertEqual(response.status_code, HTTPStatus.OK)
            self.assertTemplateUsed(response, "news/index.html")
            self.assertContains(response, "Nachricht abgesendet.")
            self.assertEqual(1, len(mail.outbox))
            self.assertEqual(
                mail.outbox[0].subject, "Kontaktformular: " + self.email_data["subject"]
            )
            self.assertEqual(mail.outbox[0].from_email, "dev@example.com")
            self.assertEqual(mail.outbox[0].to, ["info@example.com"])
            self.assertEqual(
                mail.outbox[0].body,
                self.email_data["message"] + "\n\n" + self.email_data["email"],
            )
        self.assertEqual(
            cm.output,
            [
                "INFO:spam-protection:from@example.com sent Subject, IP: 127.0.0.1, reCAPTCHA score 1337"
            ],
        )


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

    @mock.patch(
        "news.views.recaptcha.RecaptchaEnterpriseServiceClient.from_service_account_info"
    )
    def test_create_pilot(self, MockedClient):
        mocked_response = mock.MagicMock(risk_analysis=mock.MagicMock(score=1337))
        mocked_client = mock.MagicMock()
        mocked_client.create_assessment.return_value = mocked_response
        MockedClient.return_value = mocked_client

        with self.assertLogs("spam-protection", level="INFO") as cm:
            response = self.client.post(
                reverse("register"), data=self.pilot_data, follow=True
            )
            self.assertEqual(response.status_code, HTTPStatus.OK)
            self.assertTemplateUsed(response, "news/login.html")
            self.assertEqual(1, len(Pilot.objects.all()))
        self.assertEqual(
            cm.output,
            [
                "INFO:spam-protection:John Doe registered, IP: 127.0.0.1, reCAPTCHA score 1337"
            ],
        )

    @mock.patch(
        "news.views.recaptcha.RecaptchaEnterpriseServiceClient.from_service_account_info"
    )
    def test_recaptcha_failure(self, MockedClient):
        mocked_client = mock.MagicMock()
        mocked_client.create_assessment.side_effect = ValueError("Value error")
        MockedClient.return_value = mocked_client

        with self.assertLogs("spam-protection", level="INFO") as cm:
            response = self.client.post(
                reverse("register"), data=self.pilot_data, follow=True
            )
            self.assertEqual(response.status_code, HTTPStatus.OK)
            self.assertTemplateUsed(response, "news/login.html")
            self.assertEqual(1, len(Pilot.objects.all()))
        self.assertEqual(
            cm.output,
            [
                "INFO:spam-protection:Value error",
                "INFO:spam-protection:John Doe registered, IP: 127.0.0.1",
            ],
        )

    def test_required_fields_and_form_is_prefilled(self):
        for required_field in self.pilot_data.keys():
            partial_data = {
                key: value
                for key, value in self.pilot_data.items()
                if key != required_field
            }
            response = self.client.post(
                reverse("register"), data=partial_data, follow=True
            )
            self.assertEqual(response.status_code, HTTPStatus.OK)
            self.assertTemplateUsed(response, "news/register.html")
            for key, value in partial_data.items():
                if "password" in key or key == "accept_safety_concept":
                    continue
                self.assertContains(response, value)
            self.assertEqual(0, len(Pilot.objects.all()))

    def test_phone_number_validation(self):
        invalid_data = self.pilot_data.copy()
        invalid_data["phone"] = "pilot@example.com"
        response = self.client.post(reverse("register"), data=invalid_data, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/register.html")
        self.assertEqual(0, len(Pilot.objects.all()))

    def test_safety_concept_must_be_accepted(self):
        invalid_data = self.pilot_data.copy()
        invalid_data["accept_safety_concept"] = False
        response = self.client.post(reverse("register"), data=invalid_data, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/register.html")
        self.assertEqual(0, len(Pilot.objects.all()))

    def test_email_must_be_unique(self):
        pilot_data = {
            key: value
            for key, value in self.pilot_data.items()
            if key not in ["password1", "password2", "accept_safety_concept"]
        }
        Pilot.objects.create(**pilot_data)

        response = self.client.post(
            reverse("register"), data=self.pilot_data, follow=True
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/register.html")
        self.assertContains(response, "Pilot mit diesem Email existiert bereits.")
        self.assertEqual(1, len(Pilot.objects.all()))


class PilotUpdateViewTests(TestCase):
    def setUp(self):
        self.pilot_data = {
            "email": "pilot@example.com",
            "first_name": "First Name",
            "last_name": "Last Name",
            "phone": "079 123 45 67",
        }
        self.pilot = Pilot.objects.create(**self.pilot_data)
        self.client.force_login(self.pilot)

    def test_form_is_prefilled(self):
        response = self.client.get(reverse("update_pilot"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/update_pilot.html")
        for value in self.pilot_data.values():
            self.assertContains(response, value)

    def test_only_members_see_report_new_address_card(self):
        response = self.client.get(reverse("update_pilot"))
        self.assertNotContains(response, "Adressänderung melden")

        self.pilot.make_member()
        response = self.client.get(reverse("update_pilot"))
        self.assertContains(response, "Adressänderung melden")

    def test_required_fields(self):
        for required_field in self.pilot_data.keys():
            partial_data = {
                key: value
                for key, value in self.pilot_data.items()
                if key != required_field
            }
            response = self.client.post(
                reverse("update_pilot"), data=partial_data, follow=True
            )
            self.assertEqual(response.status_code, HTTPStatus.OK)
            self.assertTemplateUsed(response, "news/update_pilot.html")

    def test_phone_number_validation(self):
        invalid_data = self.pilot_data.copy()
        invalid_data["phone"] = "pilot@example.com"
        response = self.client.post(
            reverse("update_pilot"), data=invalid_data, follow=True
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/update_pilot.html")

    def test_update_member_sends_notification_email(self):
        response = self.client.post(
            reverse("update_pilot"), data=self.pilot_data, follow=True
        )
        self.assertEqual(0, len(mail.outbox))

        self.pilot_data["phone"] = "666"
        response = self.client.post(
            reverse("update_pilot"), data=self.pilot_data, follow=True
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/index.html")
        self.assertContains(response, "Änderungen gespeichert.")
        self.pilot.refresh_from_db()
        self.assertEqual(self.pilot.phone, "666")
        self.assertEqual(0, len(mail.outbox))

        self.pilot.make_member()
        self.pilot_data["phone"] = "1337"
        response = self.client.post(
            reverse("update_pilot"), data=self.pilot_data, follow=True
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/index.html")
        self.assertContains(response, "Änderungen gespeichert.")
        self.pilot.refresh_from_db()
        self.assertEqual(self.pilot.phone, "1337")
        self.assertEqual(1, len(mail.outbox))
        self.assertEqual(mail.outbox[0].subject, "Änderung an Konto")
        self.assertEqual(mail.outbox[0].from_email, "dev@example.com")
        self.assertEqual(mail.outbox[0].to, ["info@example.com"])
        self.assertTrue(self.pilot_data["first_name"] in mail.outbox[0].body)
        self.assertTrue(self.pilot_data["last_name"] in mail.outbox[0].body)
        self.assertTrue("666 -> 1337" in mail.outbox[0].body)

    def test_next_urls(self):
        response = self.client.post(
            reverse("update_pilot") + f"?next={reverse('trainings')}",
            data=self.pilot_data,
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "trainings/list_trainings.html")

        response = self.client.post(
            reverse("update_pilot") + "?next=http://danger.com",
            data=self.pilot_data,
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)


class MembershipFormViewTests(TestCase):
    def setUp(self):
        self.membership_data = {
            "street": "Street 666",
            "town": "1337 Town",
            "country": "Country",
            "request_membership": True,
            "accept_statutes": True,
            "comment": "Kommentar",
        }
        self.guest = Pilot.objects.create(
            email="guest@example.com", first_name="Guest", role=Pilot.Role.Guest
        )
        self.client.force_login(self.guest)
        self.member = Pilot.objects.create(
            email="member@example.com", role=Pilot.Role.Member
        )

    def test_required_fields_and_form_is_prefilled(self):
        for required_field in self.membership_data.keys():
            if required_field == "comment":
                continue
            partial_data = {
                key: value
                for key, value in self.membership_data.items()
                if key != required_field
            }
            response = self.client.post(
                reverse("membership"), data=partial_data, follow=True
            )
            self.assertEqual(response.status_code, HTTPStatus.OK)
            self.assertTemplateUsed(response, "news/membership.html")
            for key, value in partial_data.items():
                if key in ["request_membership", "accept_statutes"]:
                    continue
                self.assertContains(response, value)
            self.assertEqual(0, len(mail.outbox))
            self.guest.refresh_from_db()
            self.assertEqual(self.guest.role, Pilot.Role.Guest)

    def test_membership_must_be_requested(self):
        self.membership_data["request_membership"] = False
        response = self.client.post(
            reverse("membership"),
            data=self.membership_data,
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/membership.html")
        self.assertContains(response, "Du musst Mitglied werden wollen.")
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.role, Pilot.Role.Guest)

    def test_statutes_must_be_accepted(self):
        self.membership_data["accept_statutes"] = False
        response = self.client.post(
            reverse("membership"),
            data=self.membership_data,
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/membership.html")
        self.assertContains(
            response, "Du musst mit unseren Statuten einverstanden sein."
        )
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.role, Pilot.Role.Guest)

    def test_becoming_member(self):
        response = self.client.post(
            reverse("membership"), data=self.membership_data, follow=True
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/index.html")
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.role, Pilot.Role.Member)

    def test_button_and_menu_hidden_from_members(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/sidebar.html")
        self.assertContains(response, "Mitglied werden")

        self.client.force_login(self.member)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/sidebar.html")
        self.assertNotContains(response, "Mitglied werden")

    def test_form_forbidden_for_members(self):
        response = self.client.get(reverse("membership"))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(response, "news/membership.html")

        self.client.force_login(self.member)
        response = self.client.get(reverse("membership"))
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTemplateUsed(response, "403.html")


class PilotAdminTests(TestCase):
    def setUp(self):
        staff = Pilot.objects.create(email="staff@example.com", role=Pilot.Role.Staff)
        self.client.force_login(staff)
        self.pilot = Pilot.objects.create(
            email="guest@example.com", role=Pilot.Role.Guest
        )

    def test_make_member(self):
        response = self.client.post(
            reverse("admin:news_pilot_changelist"),
            data={
                "action": "make_member",
                "_selected_action": [self.pilot.id],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

        self.pilot.refresh_from_db()
        self.assertTrue(self.pilot.is_member)

    def test_make_orga(self):
        response = self.client.post(
            reverse("admin:news_pilot_changelist"),
            data={
                "action": "make_orga",
                "_selected_action": [self.pilot.id],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

        self.pilot.refresh_from_db()
        self.assertTrue(self.pilot.is_orga)

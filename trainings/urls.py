from datetime import datetime

from django.urls import path, register_converter
from django.views.generic import TemplateView

from . import views


class DateConverter:
    regex = "\d{4}-\d{2}-\d{2}"

    def to_python(self, value):
        return datetime.fromisoformat(value).date()

    def to_url(self, value):
        return value


register_converter(DateConverter, "date")

urlpatterns = [
    path("", views.TrainingListView.as_view(), name="trainings"),
    path(
        "infos/",
        TemplateView.as_view(template_name="trainings/about.html"),
        name="about_trainings",
    ),
    path("erstellen/", views.TrainingCreateView.as_view(), name="create_trainings"),
    path(
        "<date:date>/ansagen/",
        views.TrainingUpdateView.as_view(),
        name="update_training",
    ),
    path(
        "<date:date>/seepolizeimail/",
        views.EmergencyMailView.as_view(),
        name="emergency_mail",
    ),
    path("meine-trainings/", views.SignupListView.as_view(), name="my_signups"),
    path("einschreiben/", views.SignupCreateView.as_view(), name="signup"),
    path("<date:date>/einschreiben/", views.SignupCreateView.as_view(), name="signup"),
    path(
        "<date:date>/bearbeiten/",
        views.SignupUpdateView.as_view(),
        name="update_signup",
    ),
]

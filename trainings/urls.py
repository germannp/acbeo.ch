from datetime import datetime

from django.urls import path, register_converter

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
    path("einschreiben/", views.SignupCreateView.as_view(), name="signup"),
    path("meine-trainings/", views.SignupListView.as_view(), name="my_signups"),
    path("<date:date>/einschreiben/", views.SignupCreateView.as_view(), name="signup"),
    path(
        "<date:date>/bearbeiten/",
        views.SignupUpdateView.as_view(),
        name="update_signup",
    ),
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
]

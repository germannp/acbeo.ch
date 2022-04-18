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
    path("", views.RegistrationListView.as_view(), name="trainings"),
    path("signup/", views.SignupView.as_view(), name="signup"),
    path("<date:date>/signup/", views.SignupView.as_view(), name="signup"),
    path("<date:date>/update/", views.UpdateView.as_view(), name="update"),
]

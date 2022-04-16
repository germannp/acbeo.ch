from django.urls import path

from . import views


urlpatterns = [
    path("", views.RegistrationList.as_view(), name="trainings"),
]

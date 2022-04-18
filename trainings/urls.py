from django.urls import path

from . import views


urlpatterns = [
    path("", views.RegistrationListView.as_view(), name="trainings"),
    path("signup/", views.SignupView.as_view(), name="signup"),
]

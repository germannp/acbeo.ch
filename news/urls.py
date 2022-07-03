from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views


urlpatterns = [
    path("", views.PostListView.as_view(), name="home"),
    path("kontakt/", views.ContactFormView.as_view(), name="contact"),
    path("registrieren/", views.PilotCreateView.as_view(), name="register"),
    path("mitglied-werden/", views.MembershipFormView.as_view(), name="membership"),
    path("anmelden/", LoginView.as_view(template_name="news/login.html"), name="login"),
    path("abmelden/", LogoutView.as_view(), name="logout"),
    path(
        "passwort-zuruecksetzen/",
        views.PilotPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "passwort-zuruecksetzen/<uidb64>/<token>/",
        views.PilotPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("<slug:slug>/", views.PostDetailView.as_view(), name="post"),
]

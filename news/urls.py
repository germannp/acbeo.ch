from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views


urlpatterns = [
    path("", views.PostListView.as_view(), name="home"),
    path("contact/", views.ContactFormView.as_view(), name="contact"),
    path("register/", views.UserCreateView.as_view(), name="register"),
    path("login/", LoginView.as_view(template_name="news/login.html"), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("<slug:slug>/", views.PostDetailView.as_view(), name="post"),
]

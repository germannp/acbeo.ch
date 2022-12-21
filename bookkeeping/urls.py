from datetime import date

from django.urls import path, register_converter

from . import views
from trainings.urls import DateConverter


register_converter(DateConverter, "date")

urlpatterns = [
    path("", views.ReportListView.as_view(), name="reports"),
    path("<int:year>/", views.ReportListView.as_view(), name="reports"),
    path("erstellen/", views.ReportCreateView.as_view(), name="create_report"),
    path("<date:date>/", views.ReportUpdateView.as_view(), name="update_report"),
    path("run-erstellen", views.RunCreateView.as_view(), name="create_run"),
]

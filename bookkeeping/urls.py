from django.urls import path, register_converter

from . import views
from trainings.urls import DateConverter


register_converter(DateConverter, "date")

urlpatterns = [
    path("", views.ReportListView.as_view(), name="reports"),
    path("<int:year>/", views.ReportListView.as_view(), name="reports"),
    path("erstellen/", views.ReportCreateView.as_view(), name="create_report"),
    path("<date:date>/", views.ReportUpdateView.as_view(), name="update_report"),
    path("run-erstellen/", views.RunCreateView.as_view(), name="create_run"),
    path("run-bearbeiten/<int:run>/", views.RunUpdateView.as_view(), name="update_run"),
    path(
        "<date:date>/bezahlen/<int:signup>/",
        views.BillCreateView.as_view(),
        name="create_bill",
    ),
    path(
        "<date:date>/ausgabe-erfassen/",
        views.ExpenseCreateView.as_view(),
        name="create_expense",
    ),
    path(
        "<date:date>/ausgabe-bearbeiten/<int:expense>/",
        views.ExpenseUpdateView.as_view(),
        name="update_expense",
    ),
]

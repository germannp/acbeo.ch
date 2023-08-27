from django.urls import path, register_converter

from . import views
from trainings.urls import DateConverter


register_converter(DateConverter, "date")

urlpatterns = [
    path("", views.ReportListView.as_view(), name="reports"),
    path("<int:year>/", views.ReportListView.as_view(), name="reports"),
    path("bilanz/", views.BalanceView.as_view(), name="balance"),
    path("bilanz/<int:year>/", views.BalanceView.as_view(), name="balance"),
    path("pilotinnen/", views.PilotListView.as_view(), name="pilots"),
    path("pilotinnen/<int:year>/", views.PilotListView.as_view(), name="pilots"),
    path("erstellen/", views.ReportCreateView.as_view(), name="create_report"),
    path("<date:date>/", views.ReportUpdateView.as_view(), name="update_report"),
    path(
        "<date:date>/ausgabe-erfassen/",
        views.ExpenseCreateView.as_view(),
        name="create_expense",
    ),
    path(
        "<date:date>/ausgabe-bearbeiten/<int:pk>/",
        views.ExpenseUpdateView.as_view(),
        name="update_expense",
    ),
    path(
        "<date:date>/abschoepfen/",
        views.AbsorptionCreateView.as_view(),
        name="create_absorption",
    ),
    path(
        "<date:date>/abschoepfung-bearbeiten/<int:pk>/",
        views.AbsorptionUpdateView.as_view(),
        name="update_absorption",
    ),
    path("run-erstellen/", views.RunCreateView.as_view(), name="create_run"),
    path("run-bearbeiten/<int:run>/", views.RunUpdateView.as_view(), name="update_run"),
    path(
        "<date:date>/bezahlen/<int:signup>/",
        views.BillCreateView.as_view(),
        name="create_bill",
    ),
    path(
        "<date:date>/bezahlung-bearbeiten/<int:pk>/",
        views.BillUpdateView.as_view(),
        name="update_bill",
    ),
    path(
        "<date:date>/einkauf-erfassen/<int:signup>/",
        views.PurchaseCreateView.as_view(),
        name="create_purchase",
    ),
    path(
        "<date:date>/einkauf-entfernen/<int:pk>/",
        views.PurchaseDeleteView.as_view(),
        name="delete_purchase",
    ),
    path("twint/", views.TwintView.as_view(), name="twint"),
    path("meine-rechnungen/", views.BillListView.as_view(), name="bills"),
    path("meine-rechnungen/<int:year>/", views.BillListView.as_view(), name="bills"),
]

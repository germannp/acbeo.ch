import datetime

from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import generic

from .models import Report
from trainings.views import OrgaRequiredMixin
from trainings.models import Training


class ReportListView(OrgaRequiredMixin, generic.ListView):
    queryset = Report.objects.all()
    context_object_name = "reports"
    template_name = "bookkeeping/list_reports.html"


class ReportCreateView(OrgaRequiredMixin, generic.CreateView):
    model = Report
    fields = ("cash_at_start",)
    template_name = "bookkeeping/create_report.html"
    success_url = reverse_lazy("update_report", kwargs={"date": datetime.date.today()})

    def get(self, *args, **kwargs):
        """Redirect to existing report"""
        training = get_object_or_404(Training, date=datetime.date.today())
        if Report.objects.filter(training=training).exists():
            return redirect(self.success_url)

        return super().get(*args, **kwargs)

    def form_valid(self, form):
        """Fill in training or redirect to existing report"""
        training = get_object_or_404(Training, date=datetime.date.today())
        if Report.objects.filter(training=training).exists():
            return redirect(self.success_url)

        form.instance.training = training
        return super().form_valid(form)


class ReportUpdateView(OrgaRequiredMixin, generic.UpdateView):
    model = Report
    fields = ("cash_at_start", "cash_at_end")
    template_name = "bookkeeping/update_report.html"
    success_url = reverse_lazy("reports")

    def get_object(self):
        training = get_object_or_404(Training, date=self.kwargs["date"])
        return get_object_or_404(Report, training=training)

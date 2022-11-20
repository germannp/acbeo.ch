import datetime

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import generic

from .models import Report
from trainings.views import OrgaRequiredMixin
from trainings.models import Training


class ReportListView(OrgaRequiredMixin, generic.ListView):
    # I was not able to get this to work as a YearArchiveView, see
    # https://stackoverflow.com/questions/74500864.
    template_name = "bookkeeping/list_reports.html"

    def get_queryset(self):
        if not (year := self.kwargs.get("year")):
            years = Report.objects.dates("training__date", "year")
            if not years:
                raise Http404(f"Noch keine Berichte.")

            year = max([date.year for date in years])
            self.kwargs["year"] = year
        since = datetime.date(year=year, month=1, day=1)
        until = datetime.date(year=year + 1, month=1, day=1)
        reports = Report.objects.filter(
            training__date__gte=since, training__date__lt=until
        ).select_related("training")
        if not reports:
            raise Http404(f"Keine Berichte im Jahr {year}.")

        return reports

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year = self.kwargs["year"]
        context["year"] = year
        years = [date.year for date in Report.objects.dates("training__date", "year")]
        context["previous_year"] = next(
            (
                previous_year
                for previous_year in reversed(years)
                if previous_year < year
            ),
            None,
        )
        context["next_year"] = next(
            (next_year for next_year in years if year < next_year), None
        )
        return context


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

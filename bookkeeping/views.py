from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic

from . import forms
from .models import Bill, Report, Run
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
                raise Http404("Noch keine Berichte vorhanden.")

            year = max([date.year for date in years])
            self.kwargs["year"] = year
        since = date(year=year, month=1, day=1)
        until = date(year=year + 1, month=1, day=1)
        reports = (
            Report.objects.filter(training__date__gte=since, training__date__lt=until)
            .select_related("training")
            .prefetch_related("bills")
        )
        if not reports:
            raise Http404(f"Keine Berichte im Jahr {year}.")

        for previous_report, report in zip(reports, reports[1:]):
            if previous_report.cash_at_end is None:
                report.difference_between_reports = "❓"
            else:
                report.difference_between_reports = (
                    report.cash_at_start - previous_report.cash_at_end
                )
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
    success_url = reverse_lazy("update_report", kwargs={"date": date.today()})

    def get(self, *args, **kwargs):
        """Redirect to existing report"""
        training = get_object_or_404(Training, date=date.today())
        if Report.objects.filter(training=training).exists():
            return redirect(self.success_url)

        return super().get(*args, **kwargs)

    def form_valid(self, form):
        """Fill in training or redirect to existing report"""
        training = get_object_or_404(Training, date=date.today())
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["today"] = date.today()
        runs = self.object.runs.all()
        times_of_runs = sorted(set(run.created_on for run in runs))
        context["times_of_runs"] = times_of_runs
        runs_by_pilot = {}
        for pilot in self.object.training.selected_pilots:
            # Templates don't work with defaultdict, so we do nested loops.
            runs_by_pilot[pilot] = []
            for time in times_of_runs:
                runs_by_pilot[pilot].append(
                    next(
                        (
                            run
                            for run in runs
                            if run.pilot == pilot and run.created_on == time
                        ),
                        None,
                    )
                )
        context["runs_by_pilot"] = runs_by_pilot
        return context


class RunCreateView(OrgaRequiredMixin, generic.TemplateView):
    template_name = "bookkeeping/create_run.html"
    success_url = reverse_lazy("create_report")

    def get(self, *args, **kwargs):
        """Redirect to create_report if no report exists"""
        training = get_object_or_404(Training, date=date.today())
        if not Report.objects.filter(training=training).exists():
            return redirect(self.success_url)

        return super().get(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["Kind"] = Run.Kind
        training = get_object_or_404(Training, date=date.today())
        selected_pilots = training.selected_pilots
        if "formset" in context:
            formset = context["formset"]
        else:
            data = {
                "form-TOTAL_FORMS": len(selected_pilots),
                "form-INITIAL_FORMS": 0,
            }
            data.update(
                {f"form-{i}-kind": Run.Kind.Flight for i in range(len(selected_pilots))}
            )
            formset = forms.RunFormset(data)
        for form, pilot in zip(formset, selected_pilots):
            form.pilot = pilot
        context["formset"] = formset
        return context

    def post(self, request, *args, **kwargs):
        formset = forms.RunFormset(request.POST)
        if formset.is_valid():
            return self.formset_valid(formset)

        return self.render_to_response(self.get_context_data(formset=formset))

    def formset_valid(self, formset):
        training = get_object_or_404(
            Training.objects.prefetch_related("signups__pilot"),
            date=date.today(),
        )
        if not len(training.selected_pilots) == len(formset):
            messages.warning(
                self.request, "Die Anzahl der Teilnehmenden hat sich verändert."
            )
            return HttpResponseRedirect(reverse_lazy("create_run"))

        report = get_object_or_404(Report, training=training)
        created_on = timezone.now()
        for form, pilot in zip(formset, training.selected_pilots):
            form.instance.pilot = pilot
            form.instance.report = report
            form.instance.created_on = created_on
        previous_run = report.runs.order_by("created_on").last()
        formset.save()  # Only save after previous run is stored 🙄
        if previous_run and created_on - previous_run.created_on < timedelta(minutes=5):
            messages.warning(
                self.request,
                f"Run erstellt, aber Achtung, es wurde vor weniger als fünf Minuten bereits ein Run erstellt!",
            )
        else:
            messages.success(self.request, "Run erstellt.")
        return HttpResponseRedirect(self.success_url)


class RunUpdateView(OrgaRequiredMixin, generic.TemplateView):
    template_name = "bookkeeping/update_run.html"
    success_url = reverse_lazy("create_report")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["Kind"] = Run.Kind
        training = get_object_or_404(Training, date=date.today())
        report = get_object_or_404(Report, training=training)
        times_of_runs = sorted(set(run.created_on for run in report.runs.all()))
        if (num_run := self.kwargs["run"] - 1) >= len(times_of_runs):
            raise Http404(f"Kein {num_run}. Run gefunden.")

        time_of_run = times_of_runs[num_run]
        context["time_of_run"] = time_of_run
        runs = report.runs.filter(created_on=time_of_run)
        if "formset" in context:
            formset = context["formset"]
        else:
            formset = forms.RunFormset(queryset=runs)
        for form, run in zip(formset, runs):
            form.pilot = run.pilot
        context["formset"] = formset
        return context

    def post(self, request, *args, **kwargs):
        formset = forms.RunFormset(request.POST)
        if formset.is_valid() and "delete" in request.POST:
            return self.delete_run(formset)

        if formset.is_valid():
            return self.formset_valid(formset)

        return self.render_to_response(self.get_context_data(formset=formset))

    def formset_valid(self, formset):
        training = get_object_or_404(Training.objects, date=date.today())
        report = get_object_or_404(Report, training=training)
        times_of_runs = sorted(set(run.created_on for run in report.runs.all()))
        num_run = self.kwargs["run"] - 1
        runs = report.runs.filter(created_on=times_of_runs[num_run])
        for form, run in zip(formset, runs):
            form.instance.pk = run.pk
            form.instance.pilot = run.pilot
            form.instance.report = report
            form.instance.created_on = times_of_runs[num_run]
        formset.save()
        messages.success(self.request, "Run bearbeitet.")
        return HttpResponseRedirect(self.success_url)

    def delete_run(self, formset):
        training = get_object_or_404(Training, date=date.today())
        report = get_object_or_404(Report, training=training)
        times_of_runs = sorted(set(run.created_on for run in report.runs.all()))
        num_run = self.kwargs["run"] - 1
        runs = Run.objects.filter(created_on=times_of_runs[num_run])

        # Pedestrian sanity checks to reduce risk of deleting runs in parallel
        if len(formset) != len(runs):
            messages.warning(
                self.request, "Run hat sich verändert und wurde nicht gelöscht!"
            )
            return HttpResponseRedirect(self.success_url)

        for form, run in zip(formset, runs):
            if form.instance.kind == run.kind:
                continue
            messages.warning(
                self.request, "Run hat sich verändert und wurde nicht gelöscht!"
            )
            return HttpResponseRedirect(self.success_url)

        runs.delete()
        messages.success(self.request, "Run gelöscht.")
        return HttpResponseRedirect(self.success_url)


class BillCreateView(OrgaRequiredMixin, generic.CreateView):
    model = Bill
    fields = ("payed",)
    template_name = "bookkeeping/create_bill.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pilot = get_object_or_404(get_user_model(), pk=self.kwargs["pilot"])
        training = get_object_or_404(Training, date=self.kwargs["date"])
        report = get_object_or_404(Report, training=training)
        bill = Bill(pilot=pilot, report=report)
        context["bill"] = bill
        context["details"] = bill.details
        return context

    def form_valid(self, form):
        """Fill in pilot and report"""
        pilot = get_object_or_404(get_user_model(), pk=self.kwargs["pilot"])
        training = get_object_or_404(Training.objects, date=self.kwargs["date"])
        report = get_object_or_404(Report, training=training)
        if Bill.objects.filter(pilot=pilot, report=report).exists():
            messages.warning(self.request, f"{pilot} hat bereits bezahlt.")
            return HttpResponseRedirect(self.get_success_url())

        form.instance.pilot = pilot
        form.instance.report = report
        if form.instance.payed < form.instance.details["to_pay"]:
            form.add_error(
                None, f"{pilot} muss {form.instance.details['to_pay']} bezahlen."
            )
            return super().form_invalid(form)

        messages.success(self.request, f"Bezahlung von {pilot} gespeichert.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("update_report", kwargs={"date": self.kwargs["date"]})

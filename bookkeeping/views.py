from datetime import date, timedelta

from django.contrib import messages
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic

from . import forms
from .models import Bill, Expense, Report, Run
from trainings.views import OrgaRequiredMixin
from trainings.models import Signup, Training


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
            .prefetch_related("training__signups")
            .prefetch_related("bills")
            .prefetch_related("expenses")
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
    fields = ("cash_at_start", "cash_at_end", "remarks")
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
        runs_by_signup = {}
        for signup in self.object.training.selected_signups:
            # Templates don't work with defaultdict, so we do nested loops.
            runs_by_signup[signup] = []
            for time in times_of_runs:
                runs_by_signup[signup].append(
                    next(
                        (
                            run
                            for run in runs
                            if run.signup == signup and run.created_on == time
                        ),
                        None,
                    )
                )
        context["runs_by_signup"] = runs_by_signup
        return context

    def form_valid(self, form):
        if form.instance.difference < 0:
            messages.warning(self.request, "Achtung, zu wenig Geld in der Kasse.")
        if form.instance.num_unpayed_signups:
            messages.warning(self.request, "Achtung, noch nicht alle haben bezahlt.")
        return super().form_valid(form)


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
        active_signups = training.active_signups
        if "formset" in context:
            formset = context["formset"]
        else:
            data = {
                "form-TOTAL_FORMS": len(active_signups),
                "form-INITIAL_FORMS": 0,
            }
            data.update(
                {f"form-{i}-kind": Run.Kind.Flight for i in range(len(active_signups))}
            )
            formset = forms.RunFormset(data)
        for form, signup in zip(formset, active_signups):
            form.signup = signup
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
        if not len(training.active_signups) == len(formset):
            messages.warning(
                self.request, "Die Anzahl der Teilnehmenden hat sich verändert."
            )
            return HttpResponseRedirect(reverse_lazy("create_run"))

        report = get_object_or_404(Report, training=training)
        created_on = timezone.now()
        for form, signup in zip(formset, training.active_signups):
            form.instance.signup = signup
            form.instance.report = report
            form.instance.created_on = created_on
        previous_run = report.runs.order_by("created_on").last()
        formset.save()  # Only save after previous run is stored 🙄
        if previous_run and created_on - previous_run.created_on < timedelta(minutes=5):
            messages.warning(
                self.request,
                "Run erstellt, aber Achtung, es wurde vor weniger als fünf Minuten bereits ein Run erstellt!",
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
            form.signup = run.signup
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
            if run.signup.is_payed and run.kind != form.instance.kind:
                messages.warning(
                    self.request, f"{run.signup.pilot} hat bereits bezahlt."
                )
                return self.render_to_response(self.get_context_data(formset=formset))

            form.instance.pk = run.pk
            form.instance.signup = run.signup
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

        for run in runs:
            if not run.signup.is_payed:
                continue
            messages.warning(
                self.request,
                f"{run.signup.pilot} hat bereits bezahlt, Run wurde nicht gelöscht!",
            )
            return HttpResponseRedirect(self.success_url)

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


class ExpenseCreateView(OrgaRequiredMixin, generic.CreateView):
    model = Expense
    fields = ("reason", "amount")
    template_name = "bookkeeping/create_expense.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        training = get_object_or_404(Training, date=self.kwargs["date"])
        get_object_or_404(Report, training=training)
        context["date"] = self.kwargs["date"]
        return context

    def form_valid(self, form):
        """Fill in report"""
        training = get_object_or_404(Training, date=self.kwargs["date"])
        report = get_object_or_404(Report, training=training)
        form.instance.report = report
        messages.success(
            self.request,
            f"Ausgabe für {form.instance.reason} über CHF {form.instance.amount} gespeichert.",
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("update_report", kwargs={"date": self.kwargs["date"]})


class ExpenseUpdateView(OrgaRequiredMixin, generic.UpdateView):
    model = Expense
    fields = ("reason", "amount")
    template_name = "bookkeeping/update_expense.html"

    def get_object(self):
        return get_object_or_404(Expense, pk=self.kwargs["expense"])

    def post(self, request, *args, **kwargs):
        if "delete" in request.POST:
            self.get_object().delete()
            messages.success(request, "Ausgabe gelöscht.")
            return HttpResponseRedirect(self.get_success_url())

        return super().post(self, request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(
            self.request,
            f"Ausgabe für {form.instance.reason} über CHF {form.instance.amount} gespeichert.",
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("update_report", kwargs={"date": self.kwargs["date"]})


class BillCreateView(OrgaRequiredMixin, generic.CreateView):
    model = Bill
    fields = ("payed",)
    template_name = "bookkeeping/create_bill.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        signup = get_object_or_404(
            Signup.objects.select_related("training").prefetch_related("runs"),
            pk=self.kwargs["signup"],
        )
        report = get_object_or_404(Report, training=signup.training)
        bill = Bill(signup=signup, report=report)
        context["bill"] = bill
        return context

    def form_valid(self, form):
        """Fill in pilot and report"""
        signup = get_object_or_404(
            Signup.objects.select_related("training")
            .prefetch_related("runs")
            .select_related("bill"),
            pk=self.kwargs["signup"],
        )
        if signup.is_payed:
            messages.warning(self.request, f"{signup.pilot} hat bereits bezahlt.")
            return HttpResponseRedirect(self.get_success_url())

        form.instance.signup = signup
        report = get_object_or_404(Report, training=signup.training)
        form.instance.report = report
        if form.instance.payed < form.instance.to_pay:
            form.add_error(
                None, f"{signup.pilot} muss {form.instance.to_pay} bezahlen."
            )
            return super().form_invalid(form)

        messages.success(self.request, f"Bezahlung von {signup.pilot} gespeichert.")
        return super().form_valid(form)

    def get_success_url(self):
        signup = get_object_or_404(
            Signup.objects.select_related("training"), pk=self.kwargs["signup"]
        )
        return reverse_lazy("update_report", kwargs={"date": signup.training.date})

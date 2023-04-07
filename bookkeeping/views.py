from datetime import date, timedelta
from itertools import groupby

from django.db.models import prefetch_related_objects
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic

from . import forms
from .models import Bill, Expense, Purchase, Report, Run
from trainings.views import OrgaRequiredMixin
from trainings.models import Signup, Training


class YearArchiveView(generic.ListView):
    """
    Django's generic.YearArchiveView doesn't work with dates in related objects, see
    https://stackoverflow.com/questions/74500864.
    """

    filters = {}

    def get_queryset(self):
        """Get objects of the given year, default to most recent year"""
        if not (year := self.kwargs.get("year")):
            years = self.model.objects.filter(**self.filters).dates(
                self.date_field, "year"
            )
            if not years:
                raise Http404(f"Noch keine {self.name} vorhanden.")

            year = max([date.year for date in years])
            self.kwargs["year"] = year

        since = date(year=year, month=1, day=1)
        until = date(year=year + 1, month=1, day=1)
        assert self.date_field.endswith("__date")
        queryset = (
            self.model.objects.filter(**self.filters)
            .filter(
                **{self.date_field + "__gte": since, self.date_field + "__lt": until}
            )
            .select_related(self.date_field[:-6])
        )
        if not queryset:
            raise Http404(f"Keine {self.name} im Jahr {year}.")

        return queryset

    def get_context_data(self, **kwargs):
        """Add previous and next year if there are objects in them"""
        context = super().get_context_data(**kwargs)
        year = self.kwargs["year"]
        context["year"] = year
        years = [
            date.year
            for date in self.model.objects.filter(**self.filters).dates(
                self.date_field, "year"
            )
        ]
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


class ReportListView(OrgaRequiredMixin, YearArchiveView):
    model = Report
    name = "Berichte"
    date_field = "training__date"

    def get_queryset(self):
        """Prefetch & compute cash difference between consecutive reports"""
        queryset = super().get_queryset()
        prefetch_related_objects(queryset, "training__signups")
        prefetch_related_objects(queryset, "bills")
        prefetch_related_objects(queryset, "expenses")

        for previous_report, report in zip(queryset, queryset[1:]):
            if previous_report.cash_at_end is None:
                report.difference_between_reports = "❓"
            else:
                report.difference_between_reports = (
                    report.cash_at_start - previous_report.cash_at_end
                )
        return queryset


class BalanceView(OrgaRequiredMixin, YearArchiveView):
    model = Report
    name = "Berichte"
    date_field = "training__date"
    template_name = "bookkeeping/report_balance.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        prefetch_related_objects(queryset, "training__signups")
        prefetch_related_objects(queryset, "bills")
        prefetch_related_objects(queryset, "expenses")
        prefetch_related_objects(queryset, "purchases")
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Overview
        reports = sorted(
            context["report_list"], key=lambda report: report.training.date
        )
        context["num_reports"] = len(reports)
        context["num_runs"] = len(
            set(run.created_on for report in reports for run in report.runs.all())
        )
        context["num_flights"] = sum(
            run.is_flight for report in reports for run in report.runs.all()
        )
        context["num_pilots"] = len(
            set(
                signup.pilot
                for report in reports
                for signup in report.training.signups.all()
                if signup.is_paid
            )
        )
        context["latest_cash"] = (
            reports[-1].cash_at_end
            if reports[-1].cash_at_end
            else reports[-1].cash_at_start
        )

        # Revenue
        context["revenue_from_day_passes"] = {}
        context["revenue_from_equipment"] = {}
        context["revenue_from_flights"] = {}
        context["total_revenue"] = {}
        bills = [bill for report in reports for bill in report.bills.all()]
        by_method = lambda bill: bill.method
        for method, bills_paid_with_method in groupby(
            sorted(bills, key=by_method), key=by_method
        ):
            method_label = Bill.METHODS.choices[method][1]
            bills_paid_with_method = list(bills_paid_with_method)
            purchases = [
                purchase
                for bill in bills_paid_with_method
                for purchase in bill.signup.purchases.all()
            ]
            context["revenue_from_day_passes"][method_label] = sum(
                purchase.price for purchase in purchases if purchase.is_day_pass
            )
            context["revenue_from_equipment"][method_label] = sum(
                purchase.price for purchase in purchases if purchase.is_equipment
            )
            context["total_revenue"][method_label] = sum(
                bill.paid for bill in bills_paid_with_method
            )
            context["revenue_from_flights"][method_label] = (
                context["total_revenue"][method_label]
                - context["revenue_from_day_passes"][method_label]
                - context["revenue_from_equipment"][method_label]
            )

        # Expenses
        expenses = [expense for report in reports for expense in report.expenses.all()]
        context["expense_list"] = expenses
        by_reason = lambda expense: expense.reason
        context["expenses_by_reason"] = {
            reason: sum(expense.amount for expense in expenses_with_reason)
            for reason, expenses_with_reason in groupby(
                sorted(expenses, key=by_reason), key=by_reason
            )
        }
        context["total_expenses"] = sum(expense.amount for expense in expenses)
        return context


class ReportCreateView(OrgaRequiredMixin, generic.CreateView):
    model = Report
    fields = ("cash_at_start",)
    template_name = "bookkeeping/report_create.html"
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
    template_name = "bookkeeping/report_update.html"
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
        if form.instance.num_unpaid_signups:
            messages.warning(
                self.request,
                'Achtung, es haben noch nicht alle bezahlt. <a href="javascript:history.back()">Zurück</a>.',
            )
            return super().form_valid(form)

        if not (difference := form.instance.difference):
            messages.warning(
                self.request,
                'Bitte Kassenstand erfassen. <a href="javascript:history.back()">Zurück</a>.',
            )
            return super().form_valid(form)

        if difference < 0:
            messages.warning(
                self.request,
                'Achtung, zu wenig Geld in der Kasse. <a href="javascript:history.back()">Zurück</a>.',
            )
            return super().form_valid(form)

        return super().form_valid(form)


class ExpenseCreateView(OrgaRequiredMixin, generic.CreateView):
    form_class = forms.ExpenseCreateForm
    template_name = "bookkeeping/expense_create.html"

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
    template_name = "bookkeeping/expense_update.html"

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


class RunCreateView(OrgaRequiredMixin, generic.TemplateView):
    template_name = "bookkeeping/run_create.html"
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
    template_name = "bookkeeping/run_update.html"
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
            if run.signup.is_paid and run.kind != form.instance.kind:
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
            if not run.signup.is_paid:
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


class BillListView(LoginRequiredMixin, YearArchiveView):
    model = Bill
    name = "Rechnungen"
    date_field = "signup__training__date"

    @property
    def filters(self):
        return {"signup__pilot": self.request.user}

    def get_queryset(self):
        queryset = super().get_queryset()
        prefetch_related_objects(queryset, "signup__runs")
        prefetch_related_objects(queryset, "signup__purchases")

        for bill in queryset:
            bill.purchases = ", ".join(
                [purchase.description for purchase in bill.signup.purchases.all()]
            )
        return queryset


class BillCreateView(OrgaRequiredMixin, generic.CreateView):
    form_class = forms.BillForm
    template_name = "bookkeeping/bill_create.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        signup = get_object_or_404(
            Signup.objects.select_related("training").prefetch_related("runs"),
            pk=self.kwargs["signup"],
        )
        report = get_object_or_404(Report, training=signup.training)
        if signup.needs_day_pass and self.request.GET.get("day_pass") != "False":
            Purchase.save_day_pass(signup, report)
        prefetch_related_objects([signup], "purchases")
        context["bill"] = Bill(signup=signup, report=report)
        return context

    def form_valid(self, form):
        """Fill in pilot and report"""
        signup = get_object_or_404(
            Signup.objects.select_related("training")
            .prefetch_related("runs")
            .prefetch_related("purchases")
            .select_related("bill"),
            pk=self.kwargs["signup"],
        )
        if signup.is_paid:
            messages.warning(self.request, f"{signup.pilot} hat bereits bezahlt.")
            return HttpResponseRedirect(self.get_success_url())

        form.instance.signup = signup
        report = get_object_or_404(Report, training=signup.training)
        form.instance.report = report
        if form.instance.paid < form.instance.to_pay:
            form.add_error(
                None, f"{signup.pilot} muss {form.instance.to_pay} bezahlen."
            )
            return super().form_invalid(form)

        messages.success(self.request, f"Bezahlung von {signup.pilot} gespeichert.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("update_report", kwargs={"date": self.kwargs["date"]})


class BillUpdateView(OrgaRequiredMixin, generic.UpdateView):
    form_class = forms.BillForm
    template_name = "bookkeeping/bill_update.html"

    def get_object(self):
        return get_object_or_404(
            Bill.objects.select_related("signup")
            .prefetch_related("signup__runs")
            .prefetch_related("signup__purchases"),
            pk=self.kwargs["pk"],
        )

    def post(self, request, *args, **kwargs):
        if "delete" in request.POST:
            self.get_object().delete()
            messages.success(request, "Abrechnung gelöscht.")
            return HttpResponseRedirect(self.get_success_url())

        return super().post(self, request, *args, **kwargs)

    def form_valid(self, form):
        if form.instance.paid < form.instance.to_pay:
            form.add_error(
                None,
                f"{form.instance.signup.pilot} muss {form.instance.to_pay} bezahlen.",
            )
            return super().form_invalid(form)

        messages.success(
            self.request, f"Bezahlung von {form.instance.signup.pilot} gespeichert."
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("update_report", kwargs={"date": self.kwargs["date"]})


class PurchaseCreateView(OrgaRequiredMixin, generic.FormView):
    form_class = forms.PurchaseCreateForm
    template_name = "bookkeeping/purchase_create.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        signup = get_object_or_404(Signup, pk=self.kwargs["signup"])
        get_object_or_404(Report, training=signup.training)
        context["signup"] = signup
        return context

    def form_valid(self, form):
        """Fill in signup and & report, and create purchase"""
        signup = get_object_or_404(
            Signup.objects.select_related("bill"),
            pk=self.kwargs["signup"],
        )
        if signup.is_paid:
            messages.warning(self.request, f"{signup.pilot} hat bereits bezahlt.")
            return HttpResponseRedirect(reverse_lazy("create_report"))

        form.instance.signup = signup
        report = get_object_or_404(Report, training=signup.training)
        form.instance.report = report
        form.create_purchase()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy(
            "create_bill",
            kwargs={"date": self.kwargs["date"], "signup": self.kwargs["signup"]},
        )


class PurchaseDeleteView(OrgaRequiredMixin, generic.DeleteView):
    model = Purchase

    def form_valid(self, form):
        if self.object.signup.is_paid:
            messages.warning(
                self.request, f"{self.object.signup.pilot} hat bereits bezahlt."
            )
            return HttpResponseRedirect(reverse_lazy("create_report"))

        return super().form_valid(form)

    def get_success_url(self):
        purchase = self.object
        success_url = reverse_lazy(
            "create_bill",
            kwargs={"date": self.kwargs["date"], "signup": purchase.signup.pk},
        )
        if purchase.description == Purchase.DAY_PASS_DESCRIPTION:
            success_url += "?day_pass=False"
        return success_url

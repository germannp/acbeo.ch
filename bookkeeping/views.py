from datetime import date, timedelta
from itertools import groupby

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import prefetch_related_objects
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.formats import date_format
from django.views import generic

from . import forms
from .models import Absorption, Bill, Expense, PaymentMethods, Purchase, Report, Run
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
            .order_by(self.date_field)
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
        prefetch_related_objects(queryset, "absorptions")
        prefetch_related_objects(queryset, "bills__signup__purchases")
        prefetch_related_objects(queryset, "expenses")
        prefetch_related_objects(queryset, "training__signups__purchases")
        prefetch_related_objects(queryset, "training__signups__runs")
        prefetch_related_objects(queryset, "training__signups__bill")
        prefetch_related_objects(queryset, "training__signups__pilot")
        prefetch_related_objects(queryset, "runs")

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
        prefetch_related_objects(queryset, "absorptions__signup__pilot")
        prefetch_related_objects(queryset, "bills__signup__pilot")
        prefetch_related_objects(queryset, "bills__signup__purchases")
        prefetch_related_objects(queryset, "expenses")
        prefetch_related_objects(queryset, "training__signups__purchases")
        prefetch_related_objects(queryset, "training__signups__runs")
        prefetch_related_objects(queryset, "training__signups__bill")
        prefetch_related_objects(queryset, "training__signups__pilot")
        prefetch_related_objects(queryset, "runs")
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Overview
        reports = sorted(
            context["report_list"], key=lambda report: report.training.date
        )
        context["num_reports"] = len(reports)
        runs = [run for report in reports for run in report.runs.all()]
        context["num_runs"] = len(set(run.created_on for run in runs))
        context["num_flights"] = sum(run.is_flight for run in runs)
        signups = [
            signup for report in reports for signup in report.training.signups.all()
        ]
        context["num_pilots"] = len(
            set(signup.pilot for signup in signups if signup.is_paid)
        )
        context["num_open_signups"] = sum(signup.must_be_paid for signup in signups)

        # Revenue
        context["revenue_from_absorptions"] = {}
        context["revenue_from_day_passes"] = {}
        context["revenue_from_prepaid_flights"] = {}
        context["revenue_from_flights"] = {}
        context["revenue_from_equipment"] = {}
        context["total_revenue"] = {}
        absorptions = [
            absorption for report in reports for absorption in report.absorptions.all()
        ]
        bills = [bill for report in reports for bill in report.bills.all()]
        for method in PaymentMethods:
            if method == PaymentMethods.BANK_TRANSFER:
                continue

            absorptions_paid_with_method = [
                absorption for absorption in absorptions if absorption.method == method
            ]
            context["revenue_from_absorptions"][method.label] = sum(
                absorption.amount for absorption in absorptions_paid_with_method
            )

            bills_paid_with_method = [bill for bill in bills if bill.method == method]
            purchases = [
                purchase
                for bill in bills_paid_with_method
                for purchase in bill.signup.purchases.all()
            ]
            context["revenue_from_day_passes"][method.label] = sum(
                purchase.price for purchase in purchases if purchase.is_day_pass
            )
            context["revenue_from_prepaid_flights"][method.label] = sum(
                purchase.price for purchase in purchases if purchase.is_prepaid_flights
            )
            context["revenue_from_equipment"][method.label] = sum(
                purchase.price for purchase in purchases if purchase.is_equipment
            )
            context["total_revenue"][method.label] = (
                sum(bill.amount for bill in bills_paid_with_method)
                + context["revenue_from_absorptions"][method.label]
            )
            context["revenue_from_flights"][method.label] = (
                context["total_revenue"][method.label]
                - context["revenue_from_absorptions"][method.label]
                - context["revenue_from_day_passes"][method.label]
                - context["revenue_from_prepaid_flights"][method.label]
                - context["revenue_from_equipment"][method.label]
            )

        # Expeditures
        expeditures = absorptions + [
            expense for report in reports for expense in report.expenses.all()
        ]
        by_reason = lambda expediture: expediture.reason
        context["expeditures_by_reason"] = {
            reason: sum(expediture.amount for expediture in expeditures_with_reason)
            for reason, expeditures_with_reason in groupby(
                sorted(expeditures, key=by_reason), key=by_reason
            )
        }
        context["total_expeditures"] = sum(
            expediture.amount for expediture in expeditures
        )
        by_date = lambda expediture: expediture.report.training.date
        context["expediture_list"] = sorted(
            [expediture for expediture in expeditures if expediture.amount], key=by_date
        )

        # Amount
        context["first_cash"] = reports[0].cash_at_start
        if reports[-1].cash_at_end is not None:
            context["latest_cash"] = reports[-1].cash_at_end
            context["amount"] = reports[-1].cash_at_end - (
                reports[0].cash_at_start
                + context["total_revenue"].get(PaymentMethods.CASH.label, 0)
                - context.get("total_expeditures", 0)
            )

        # Bank transfers
        context["bank_transfers"] = [
            absorption
            for absorption in absorptions
            if absorption.method == PaymentMethods.BANK_TRANSFER and absorption.amount
        ]

        # TWINT
        transactions = absorptions + bills
        transactions = [
            transaction
            for transaction in transactions
            if transaction.method == PaymentMethods.TWINT and transaction.amount
        ]
        by_week = lambda expediture: int(expediture.report.training.date.strftime("%W"))
        twint_by_week = {
            week: sorted(transactions_in_week, key=by_date)
            for week, transactions_in_week in groupby(
                sorted(transactions, key=by_week), key=by_week
            )
        }

        def label(week, transactions_in_week):
            monday = date.fromisocalendar(reports[0].training.date.year, week, 1)
            sunday = date.fromisocalendar(reports[0].training.date.year, week, 7)
            total = sum(transaction.amount for transaction in transactions_in_week)
            return f"{date_format(monday, 'j.n.')} - {date_format(sunday, 'j.n.')}, Total {total}"

        context["twint_weeks"] = {
            label(week, transactions_in_week): transactions_in_week
            for week, transactions_in_week in twint_by_week.items()
        }
        return context


class ReportCreateView(OrgaRequiredMixin, generic.CreateView):
    form_class = forms.ReportCreateForm
    template_name = "bookkeeping/report_create.html"

    def get(self, *args, **kwargs):
        """Redirect to existing report"""
        today = timezone.now().date()
        training = get_object_or_404(Training, date=today)
        if Report.objects.filter(training=training).exists():
            return redirect(self.get_success_url())

        if not training.emergency_mail_sender:
            messages.warning(
                self.request, "Es wurde noch kein Seepolizeimail abgesendet!"
            )
            return redirect(
                reverse_lazy("emergency_mail", kwargs={"date": today})
                + f"?next={reverse_lazy('create_report')}"
            )

        return super().get(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        training = get_object_or_404(Training, date=today)
        prefetch_related_objects([training], "signups__pilot")
        prefetch_related_objects([training], "signups__bill")
        if new_pilots := training.new_pilots:
            names = [pilot.first_name for pilot in new_pilots]
            label = (", ".join(names[:-1]) + " und ") * (len(names) >= 2) + names[-1]
            context["new_pilots"] = label
        return context

    def form_valid(self, form):
        """Fill in training or redirect to existing report"""
        today = timezone.now().date()
        training = get_object_or_404(Training, date=today)
        if Report.objects.filter(training=training).exists():
            return redirect(self.get_success_url())

        form.instance.training = training

        if not form.cleaned_data["sufficient_parking_tickets"]:
            messages.warning(
                self.request, "Bitte im Tourismusbüro neue Parkkarten besorgen."
            )

        prefetch_related_objects([training], "signups__pilot")
        prefetch_related_objects([training], "signups__bill")
        if training.new_pilots and not form.cleaned_data["briefing"]:
            messages.warning(
                self.request, "Bitte Briefing vor dem ersten Flug durchführen."
            )

        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy(
            "update_report", kwargs={"date": timezone.localtime().date()}
        )


class ReportUpdateView(OrgaRequiredMixin, generic.UpdateView):
    model = Report
    fields = ("cash_at_start", "cash_at_end", "remarks")
    template_name = "bookkeeping/report_update.html"
    success_url = reverse_lazy("reports")

    def get_object(self):
        training = get_object_or_404(Training, date=self.kwargs["date"])
        report = get_object_or_404(
            Report.objects.select_related("training")
            .prefetch_related("training__signups__pilot")
            .prefetch_related("runs__signup")
            .prefetch_related("expenses")
            .prefetch_related("absorptions"),
            training=training,
        )
        return report

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["today"] = timezone.now().date()
        runs = self.object.runs.all()
        times_of_runs = sorted(set(run.created_on for run in runs))
        context["times_of_runs"] = times_of_runs
        runs_by_signup = {}
        signups = self.object.training.selected_signups
        prefetch_related_objects(signups, "pilot")
        prefetch_related_objects(signups, "bill")
        for signup in signups:
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
        prefetch_related_objects([form.instance], "training__signups__bill")
        prefetch_related_objects([form.instance], "training__signups__purchases")
        if form.instance.num_unpaid_signups:
            messages.warning(self.request, "Es haben noch nicht alle bezahlt.")
            self.success_url = reverse_lazy(
                "update_report", kwargs={"date": form.instance.training.date}
            )
            return super().form_valid(form)

        if form.instance.cash_at_end is None:
            messages.warning(self.request, "Bitte Kassenstand erfassen.")
            self.success_url = reverse_lazy(
                "update_report", kwargs={"date": form.instance.training.date}
            )
            return super().form_valid(form)

        if form.instance.difference < 0:
            messages.warning(
                self.request,
                'Zu wenig Geld in der Kasse. <a href="javascript:history.back()">Zurück</a>.',
            )
            self.success_url = reverse_lazy(
                "update_report", kwargs={"date": form.instance.training.date}
            )
            return super().form_valid(form)

        messages.success(
            self.request, "Alle haben bezahlt und der Kassenstand ist gespeichert 😊"
        )
        training_is_today = form.instance.training.date == timezone.localtime().date()
        finishing_early = timezone.localtime().hour < 17
        if training_is_today and finishing_early:
            messages.warning(
                self.request,
                "Falls das Training frühzeitig abgebrochen wurde, sollte insbesondere bei starkem "
                'Wind die Seelpolizei unter <a href="tel:+41316387676">+41 31 638 76 76</a> '
                "benachrichtigt werden, dass unser Boot nicht mehr vor Ort ist.",
            )
        return super().form_valid(form)


class ExpenseCreateView(OrgaRequiredMixin, generic.CreateView):
    form_class = forms.ExpenseCreateForm
    template_name = "bookkeeping/expense_create.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        training = get_object_or_404(Training, date=self.kwargs["date"])
        get_object_or_404(Report, training=training)
        return context

    def form_valid(self, form):
        """Fill in report"""
        training = get_object_or_404(Training, date=self.kwargs["date"])
        report = get_object_or_404(Report, training=training)
        form.instance.report = report
        messages.success(
            self.request,
            f"Ausgabe für {form.instance.reason} über Fr. {form.instance.amount} gespeichert.",
        )
        form.sender = self.request.user
        form.send_mail()
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
            f"Ausgabe für {form.instance.reason} über Fr. {form.instance.amount} gespeichert.",
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("update_report", kwargs={"date": self.kwargs["date"]})


class AbsorptionCreateView(OrgaRequiredMixin, generic.CreateView):
    form_class = forms.AbsorptionForm
    template_name = "bookkeeping/absorption_create.html"

    def get_context_data(self, **kwargs):
        """Fill in selected signups"""
        context = super().get_context_data(**kwargs)
        training = get_object_or_404(Training, date=self.kwargs["date"])
        selected_signups = training.signups.filter(
            status=Signup.Status.SELECTED
        ).select_related("pilot")
        context["form"].fields["signup"].queryset = selected_signups
        if user_signup := next(
            (
                signup
                for signup in selected_signups
                if signup.pilot == self.request.user
            ),
            None,
        ):
            context["form"].fields["signup"].initial = user_signup
        else:
            context["form"].fields["signup"].initial = selected_signups.first()
        get_object_or_404(Report, training=training)
        return context

    def form_valid(self, form):
        """Fill in report & check sanity"""
        training = get_object_or_404(Training, date=self.kwargs["date"])
        report = get_object_or_404(Report, training=training)
        if form.instance.amount > (cash := report.cash_at_start + report.cash_revenue):
            form.add_error(None, f"Man kann höchstens Fr. {cash} abschöpfen.")
            return super().form_invalid(form)

        form.instance.report = report
        messages.success(
            self.request,
            f"Abschöpfung von {form.instance.signup.pilot} über Fr. {form.instance.amount} gespeichert.",
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("update_report", kwargs={"date": self.kwargs["date"]})


class AbsorptionUpdateView(OrgaRequiredMixin, generic.UpdateView):
    model = Absorption
    form_class = forms.AbsorptionForm
    template_name = "bookkeeping/absorption_update.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        training = get_object_or_404(Training, date=self.kwargs["date"])
        context["form"].fields["signup"].queryset = training.signups.filter(
            status=Signup.Status.SELECTED
        ).select_related("pilot")
        get_object_or_404(Report, training=training)
        return context

    def post(self, request, *args, **kwargs):
        if "delete" in request.POST:
            self.get_object().delete()
            messages.success(request, "Abschöpfung gelöscht.")
            return HttpResponseRedirect(self.get_success_url())

        return super().post(self, request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(
            self.request,
            f"Abschöpfung von {form.instance.signup.pilot} über Fr. {form.instance.amount} gespeichert.",
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("update_report", kwargs={"date": self.kwargs["date"]})


class RunCreateView(OrgaRequiredMixin, generic.TemplateView):
    template_name = "bookkeeping/run_create.html"
    success_url = reverse_lazy("create_report")

    def get(self, *args, **kwargs):
        """Redirect to create_report if no report exists"""
        training = get_object_or_404(Training, date=timezone.now().date())
        if not Report.objects.filter(training=training).exists():
            return redirect(self.success_url)

        return super().get(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["Kind"] = Run.Kind
        training = get_object_or_404(
            Training.objects.prefetch_related("signups__pilot"),
            date=timezone.now().date(),
        )
        active_signups = training.active_signups
        prefetch_related_objects(active_signups, "pilot")
        if "formset" in context:
            formset = context["formset"]
        else:
            data = {
                "form-TOTAL_FORMS": len(active_signups),
                "form-INITIAL_FORMS": 0,
            }
            data.update(
                {f"form-{i}-kind": Run.Kind.FLIGHT for i in range(len(active_signups))}
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
            date=timezone.now().date(),
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
        if previous_run and created_on - previous_run.created_on < timedelta(
            minutes=30
        ):
            messages.warning(
                self.request,
                "Run erstellt, aber Achtung, es wurde vor weniger als einer halben Stunde bereits ein Run erstellt!",
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
        training = get_object_or_404(Training, date=timezone.now().date())
        report = get_object_or_404(Report, training=training)
        times_of_runs = sorted(set(run.created_on for run in report.runs.all()))
        if (num_run := self.kwargs["run"] - 1) >= len(times_of_runs):
            raise Http404(f"Kein {num_run}. Run gefunden.")

        time_of_run = times_of_runs[num_run]
        context["time_of_run"] = time_of_run
        runs = report.runs.filter(created_on=time_of_run)
        prefetch_related_objects(runs, "signup__pilot")
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
        training = get_object_or_404(Training.objects, date=timezone.now().date())
        report = get_object_or_404(Report, training=training)
        times_of_runs = sorted(set(run.created_on for run in report.runs.all()))
        num_run = self.kwargs["run"] - 1
        runs = (
            Run.objects.filter(created_on=times_of_runs[num_run])
            .prefetch_related("signup__bill")
            .prefetch_related("signup__pilot")
        )
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
        training = get_object_or_404(Training, date=timezone.now().date())
        report = get_object_or_404(Report, training=training)
        times_of_runs = sorted(set(run.created_on for run in report.runs.all()))
        num_run = self.kwargs["run"] - 1
        runs = (
            Run.objects.filter(created_on=times_of_runs[num_run])
            .prefetch_related("signup__bill")
            .prefetch_related("signup__pilot")
        )

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
        prefetch_related_objects(queryset, "signup__training__report")

        for bill in queryset:
            bill.purchases = ", ".join(
                [purchase.description for purchase in bill.signup.purchases.all()]
            )
        return queryset


class PilotListView(OrgaRequiredMixin, YearArchiveView):
    model = Bill
    name = "aktive Pilot·innen"
    date_field = "signup__training__date"
    template_name = "bookkeeping/pilot_list.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        prefetch_related_objects(queryset, "signup__pilot")
        prefetch_related_objects(queryset, "signup__runs")
        prefetch_related_objects(queryset, "signup__training__report")
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        stats = {}
        by_pilots_pk = lambda bill: bill.signup.pilot.pk
        for _, bills in groupby(
            sorted(context["bill_list"], key=by_pilots_pk), key=by_pilots_pk
        ):
            bills = list(bills)
            pilot = bills[0].signup.pilot
            stats[pilot] = [
                len(bills),
                sum(bill.num_flights for bill in bills),
                sum(bill.num_services for bill in bills),
            ]

        by_numbers = lambda item: item[1]
        by_name = lambda item: str(item[0])
        context["stats_by_pilot"] = dict(
            sorted(sorted(stats.items(), key=by_name), key=by_numbers, reverse=True)
        )
        return context


class BillCreateView(OrgaRequiredMixin, generic.CreateView):
    form_class = forms.BillForm
    template_name = "bookkeeping/bill_create.html"

    def get(self, *args, **kwargs):
        """Redirect if paid"""
        signup = get_object_or_404(
            Signup.objects.select_related("bill"), pk=self.kwargs["signup"]
        )
        if signup.is_paid:
            messages.warning(self.request, f"{signup.pilot} hat bereits bezahlt.")
            return redirect(self.get_report_url())

        old_signups = (
            Signup.objects.filter(
                pilot=signup.pilot,
                training__date__year=signup.training.date.year,
                training__date__lt=signup.training.date,
            )
            .select_related("bill")
            .select_related("training")
            .prefetch_related("runs__signup__pilot")
            .prefetch_related("purchases")
            .order_by("training__date")
        )
        for old_signup in old_signups:
            if old_signup.must_be_paid:
                url = reverse_lazy(
                    "create_bill",
                    kwargs={"date": old_signup.training.date, "signup": old_signup.pk},
                )
                date = date_format(old_signup.training.date, "l, j. F")
                messages.warning(
                    self.request,
                    f'{old_signup.pilot} wurde für <a href="{url}">{date}</a>, nicht abgerechnet.',
                )

        return super().get(*args, **kwargs)

    def get_context_data(self, **kwargs):
        """Prepare Bill"""
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
        """Deal with training orgas and fill in pilot and report"""
        signup = get_object_or_404(
            Signup.objects.select_related("training")
            .prefetch_related("runs")
            .prefetch_related("purchases")
            .select_related("bill"),
            pk=self.kwargs["signup"],
        )
        if signup.is_paid:
            messages.warning(self.request, f"{signup.pilot} hat bereits bezahlt.")
            return HttpResponseRedirect(self.get_report_url())

        report = get_object_or_404(Report, training=signup.training)
        if "make-orga" in self.request.POST:
            if signup.is_training_orga:
                messages.warning(self.request, "Ist bereits Tagesleiter·in.")
                return super().form_invalid(form)

            if not report.orga_1:
                report.orga_1 = signup
                report.save()
                messages.success(self.request, "Zu Tagesleiter·in gemacht.")
                return super().form_invalid(form)

            if not report.orga_2:
                report.orga_2 = signup
                report.save()
                messages.success(self.request, "Zu Tagesleiter·in gemacht.")
                return super().form_invalid(form)

            messages.warning(
                self.request,
                f"Nicht zu Tagesleiter·in gemacht, {report.orga_1.pilot} und "
                f"{report.orga_2.pilot} sind bereits als Tagesleiter·innen gespeichert.",
            )
            return super().form_invalid(form)

        if "undo-orga" in self.request.POST:
            signup = get_object_or_404(
                Signup.objects.select_related("bill"), pk=self.kwargs["signup"]
            )
            if signup.is_paid:
                messages.warning(
                    self.request,
                    f"Tagesleiter·in nicht entfernt, {signup.pilot} hat bereits bezahlt.",
                )
                return HttpResponseRedirect(self.get_report_url())

            if report.orga_1 == signup:
                report.orga_1 = report.orga_2
                report.orga_2 = None
                report.save()
            if report.orga_2 == signup:
                report.orga_2 = None
                report.save()
            messages.warning(self.request, "Tagesleiter·in entfernt.")
            return super().form_invalid(form)

        form.instance.signup = signup
        form.instance.report = report
        if form.instance.amount < form.instance.to_pay:
            form.add_error(
                None, f"{signup.pilot} muss Fr. {form.instance.to_pay} bezahlen."
            )
            return super().form_invalid(form)

        messages.success(self.request, f"Bezahlung von {signup.pilot} gespeichert.")
        success_url = self.get_report_url()
        if form.instance.amount and form.instance.method == PaymentMethods.TWINT:
            success_url = (
                reverse_lazy("twint")
                + f"?betrag={form.instance.amount}&next={success_url}"
            )
        self.success_url = success_url
        return super().form_valid(form)

    def get_report_url(self):
        return reverse_lazy("update_report", kwargs={"date": self.kwargs["date"]})


class TwintView(generic.TemplateView):
    template_name = "bookkeeping/twint.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["amount"] = self.request.GET.get("betrag")
        return context

    def get_success_url(self):
        return self.request.GET.get("next")


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
            return HttpResponseRedirect(self.get_report_url())

        return super().post(self, request, *args, **kwargs)

    def form_valid(self, form):
        if form.instance.amount < form.instance.to_pay:
            form.add_error(
                None,
                f"{form.instance.signup.pilot} muss Fr. {form.instance.to_pay} bezahlen.",
            )
            return super().form_invalid(form)

        messages.success(
            self.request, f"Bezahlung von {form.instance.signup.pilot} gespeichert."
        )
        success_url = self.get_report_url()
        if form.instance.amount and form.instance.method == PaymentMethods.TWINT:
            success_url = (
                reverse_lazy("twint")
                + f"?betrag={form.instance.amount}&next={success_url}"
            )
        self.success_url = success_url
        return super().form_valid(form)

    def get_report_url(self):
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

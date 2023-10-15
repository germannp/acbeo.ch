from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import prefetch_related_objects
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.formats import date_format
from django.views import generic

from . import forms
from .models import Signup, Training


class TrainingListView(LoginRequiredMixin, generic.ListView):
    paginate_by = 4

    def get_queryset(self):
        trainings = Training.objects.filter(
            date__gte=timezone.now().date()
        ).prefetch_related("signups__pilot")
        for training in trainings:
            training.select_signups()
        # Selecting signups can alter their order, but Signup instances cannot be
        # sorted. Refreshing them from the DB is the best solution I found 🤷
        trainings = Training.objects.filter(
            date__gte=timezone.now().date()
        ).prefetch_related("signups__pilot")
        return trainings

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        context["day_after_tomorrow"] = today + timedelta(days=2)
        context["today"] = today
        return context


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class TrainingCreateView(StaffRequiredMixin, generic.FormView):
    form_class = forms.TrainingCreateForm
    template_name = "trainings/training_create.html"
    success_url = reverse_lazy("trainings")

    def form_valid(self, form):
        form.create_trainings()
        return super().form_valid(form)


class OrgaRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_orga


class TrainingUpdateView(OrgaRequiredMixin, generic.UpdateView):
    form_class = forms.TrainingUpdateForm
    template_name = "trainings/training_update.html"

    def get_object(self):
        if self.kwargs["date"] < timezone.now().date():
            raise Http404("Vergangene Trainings können nicht bearbeitet werden.")
        return get_object_or_404(Training, date=self.kwargs["date"])

    def get_success_url(self):
        success_url = reverse_lazy("trainings")
        if page := self.request.GET.get("page"):
            success_url += f"?page={page}"
        if training := self.request.GET.get("training"):
            success_url += f"#training_{training}"
        return success_url


class EmergencyMailView(OrgaRequiredMixin, SuccessMessageMixin, generic.UpdateView):
    form_class = forms.EmergencyMailForm
    template_name = "trainings/emergency_mail.html"
    success_url = reverse_lazy("trainings")
    success_message = "Seepolizeimail abgesendet."

    def get_object(self):
        today = timezone.now().date()
        if self.kwargs["date"] < today:
            raise Http404(
                "Seepolizeimail kann nicht für vergangene Trainings versandt werden."
            )
        if self.kwargs["date"] > today + timedelta(days=2):
            raise Http404(
                "Seepolizeimail kann höchstens drei Tage im Voraus versandt werden."
            )

        training = get_object_or_404(
            Training.objects.prefetch_related("signups__pilot"),
            date=self.kwargs["date"],
        )
        if sender := training.emergency_mail_sender:
            messages.info(
                self.request, f"{sender} hat bereits ein Seepolizeimail versandt."
            )

        prefetch_related_objects([training], "signups__pilot")
        prefetch_related_objects([training], "signups__bill")
        if self.request.method == "GET" and (new_pilots := training.new_pilots):
            names = sorted(pilot.first_name for pilot in new_pilots)
            message = (", ".join(names[:-1]) + " und ") * (len(names) >= 2) + names[-1]
            message += " ist" if len(new_pilots) == 1 else " sind"
            message += " zum ersten Mal dabei."
            messages.info(self.request, message)

        training.select_signups()
        return training

    def form_valid(self, form):
        if form.instance.emergency_mail_sender:
            return redirect(self.success_url)

        form.sender = self.request.user
        form.send_mail()
        return super().form_valid(form)

    def get_success_url(self):
        if success_url := self.request.GET.get("next"):
            return success_url

        return self.success_url


class SignupListView(LoginRequiredMixin, generic.ListView):
    model = Signup

    def get_queryset(self):
        today = timezone.now().date()
        queryset = (
            Signup.objects.filter(pilot=self.request.user, training__date__gte=today)
            .select_related("training")
            .prefetch_related("training__signups__pilot")
        )
        for signup in queryset:
            signup.training.select_signups()
        # After selecting signups, they have to be refreshed from the DB
        queryset = (
            Signup.objects.filter(pilot=self.request.user, training__date__gte=today)
            .order_by("training__date")
            .select_related("training")
            .prefetch_related("training__signups")
        )
        return queryset


class SignupCreateView(LoginRequiredMixin, SuccessMessageMixin, generic.CreateView):
    form_class = forms.SignupCreateForm
    template_name = "trainings/signup_create.html"

    def get_initial(self):
        """Set default date based on url pattern"""
        if "date" in self.kwargs:
            return {"date": self.kwargs["date"].isoformat()}

        today = timezone.now().date()
        if today.weekday() >= 5:  # Saturdays and Sundays
            return {"date": today.isoformat()}

        next_saturday = today + timedelta(days=(5 - today.weekday()) % 7)
        return {"date": next_saturday.isoformat()}

    def form_valid(self, form):
        """Fill in pilot and training"""
        pilot = self.request.user
        self.date = form.cleaned_data["date"]
        if Training.objects.filter(date=self.date).exists():
            training = Training.objects.get(date=self.date)
        else:
            wednesday_before = self.date + timedelta(
                days=(2 - self.date.weekday()) % 7 - 7
            )
            training = Training.objects.create(
                date=self.date, priority_date=wednesday_before
            )
        if Signup.objects.filter(pilot=pilot, training=training).exists():
            form.add_error(
                None,
                f"Du bist für <b>{date_format(self.date, 'l')}</b>, den "
                f"{date_format(self.date, 'j. F Y')}, bereits eingeschrieben.",
            )
            return super().form_invalid(form)

        form.instance.pilot = pilot
        form.instance.training = training
        return super().form_valid(form)

    def get_cancel_url(self):
        cancel_url = reverse_lazy("trainings")
        if page := self.request.GET.get("page"):
            cancel_url += f"?page={page}"
        if training := self.request.GET.get("training"):
            cancel_url += f"#training_{training}"
        return cancel_url

    def get_success_url(self):
        self.success_message = (
            f"Eingeschrieben für <b>{date_format(self.date, 'l')}</b>, "
            f"den {date_format(self.date, 'j. F Y')}."
        )
        next_day = self.date + timedelta(days=1)
        success_url = reverse_lazy("signup", kwargs={"date": next_day})
        if page := self.request.GET.get("page"):
            success_url += f"?page={page}"
        if training := self.request.GET.get("training"):
            success_url += f"&training={training}"
        return success_url


class SignupUpdateView(LoginRequiredMixin, generic.UpdateView):
    form_class = forms.SignupUpdateForm
    template_name = "trainings/signup_update.html"

    def get_object(self):
        if self.kwargs["date"] < timezone.now().date():
            raise Http404("Vergangene Anmeldungen können nicht bearbeitet werden.")
        pilot = self.request.user
        training = get_object_or_404(Training, date=self.kwargs["date"])
        signup = get_object_or_404(Signup, pilot=pilot, training=training)
        if "cancel" in self.request.POST:
            signup.cancel()
        elif "resignup" in self.request.POST:
            signup.resignup()
        return signup

    def get_success_url(self):
        if (success_url := self.request.GET.get("next")) == reverse_lazy("signups"):
            return success_url

        success_url = reverse_lazy("trainings")
        if page := self.request.GET.get("page"):
            success_url += f"?page={page}"
        if training := self.request.GET.get("training"):
            success_url += f"#training_{training}"
        return success_url

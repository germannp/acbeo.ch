from datetime import datetime, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import generic

from . import forms
from .models import Training, Signup


class TrainingListView(LoginRequiredMixin, generic.ListView):
    context_object_name = "trainings"
    paginate_by = 4
    template_name = "trainings/list_trainings.html"

    def get_queryset(self):
        trainings = Training.objects.filter(date__gte=datetime.now()).prefetch_related(
            "signups__pilot"
        )
        for training in trainings:
            training.select_signups()
        return trainings

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["day_after_tomorrow"] = datetime.now().date() + timedelta(days=2)
        return context


class TrainingUpdateView(LoginRequiredMixin, generic.UpdateView):
    form_class = forms.TrainingUpdateForm
    template_name = "trainings/update_training.html"
    success_url = reverse_lazy("trainings")

    def get_object(self):
        return get_object_or_404(Training, date=self.kwargs["date"])


class TrainingCreateView(LoginRequiredMixin, generic.FormView):
    form_class = forms.TrainingCreateForm
    template_name = "trainings/create_trainings.html"
    success_url = reverse_lazy("trainings")

    def form_valid(self, form):
        form.create_trainings()
        return super().form_valid(form)


class EmergencyMailView(LoginRequiredMixin, SuccessMessageMixin, generic.UpdateView):
    form_class = forms.EmergencyMailForm
    template_name = "trainings/emergency_mail.html"
    success_url = reverse_lazy("trainings")
    success_message = "Seepolizeimail abgesendet."

    def get_object(self):
        return get_object_or_404(Training, date=self.kwargs["date"])

    def form_valid(self, form):
        today = datetime.now().date()
        if form.instance.date < today:
            form.add_error(
                None,
                "Seepolizeimail kann nicht für vergangene Trainings versandt werden.",
            )
            return super().form_invalid(form)
        if form.instance.date > today + timedelta(days=2):
            form.add_error(
                None,
                "Seepolizeimail kann höchstens drei Tage im Voraus versandt werden.",
            )
            return super().form_invalid(form)
        form.sender = self.request.user
        form.send_mail()
        return super().form_valid(form)


class SignupListView(LoginRequiredMixin, generic.ListView):
    context_object_name = "future_and_past_signups"
    template_name = "trainings/list_signups.html"

    def get_queryset(self):
        today = datetime.now().date()
        future_signups = (
            Signup.objects.filter(pilot=self.request.user)
            .filter(training__date__gte=today)
            .select_related("training")
        )
        for signup in future_signups:
            signup.training.select_signups()
        # After selecting signups, they have to be refreshed from the DB
        signups = (
            Signup.objects.filter(pilot=self.request.user)
            .order_by("training__date")
            .select_related("training")
        )
        future_signups = [signup for signup in signups if signup.training.date >= today]
        past_signups = [signup for signup in signups if signup.training.date < today][::-1]
        return {"future": future_signups, "past": past_signups}


class SignupCreateView(LoginRequiredMixin, SuccessMessageMixin, generic.CreateView):
    form_class = forms.SignupCreateForm
    template_name = "trainings/signup.html"

    def get_context_data(self, **kwargs):
        """Set default date based on url pattern"""
        context = super().get_context_data(**kwargs)
        if "date" in self.kwargs:
            context["date"] = self.kwargs["date"]
        else:
            today = datetime.now().date()
            next_saturday = today + timedelta(days=(5 - today.weekday()) % 7)
            context["date"] = next_saturday
        return context

    def form_valid(self, form):
        """Fill in pilot from logged in user and check sanity"""
        self.date = datetime.fromisoformat(form.data["date"]).date()
        today = datetime.now().date()
        if self.date < today:
            form.add_error(None, "Einschreiben ist nur für kommende Trainings möglich.")
            return super().form_invalid(form)
        if self.date > today + timedelta(days=365):
            form.add_error(
                None, "Einschreiben ist höchstens ein Jahr im Voraus möglich."
            )
            return super().form_invalid(form)
        if Training.objects.filter(date=self.date).exists():
            training = Training.objects.get(date=self.date)
        else:
            wednesday_before = self.date + timedelta(
                days=(2 - self.date.weekday()) % 7 - 7
            )
            training = Training.objects.create(
                date=self.date, priority_date=wednesday_before
            )
        pilot = self.request.user
        if Signup.objects.filter(pilot=pilot, training=training).exists():
            form.add_error(None, f"Du bist für {self.date} bereits eingeschrieben.")
            return super().form_invalid(form)
        form.instance.pilot = pilot
        form.instance.training = training
        return super().form_valid(form)

    def get_success_url(self):
        self.success_message = f"Eingeschrieben für {self.date}."
        next_day = self.date + timedelta(days=1)
        return reverse_lazy("signup", kwargs={"date": next_day})


class SignupUpdateView(LoginRequiredMixin, generic.UpdateView):
    form_class = forms.SignupUpdateForm
    template_name = "trainings/update_signup.html"

    def get_object(self):
        pilot = self.request.user
        training = get_object_or_404(Training, date=self.kwargs["date"])
        signup = get_object_or_404(Signup, pilot=pilot, training=training)
        if "cancel" in self.request.POST:
            signup.cancel()
        elif "resignup" in self.request.POST:
            signup.resignup()
        return signup

    def form_valid(self, form):
        if self.kwargs["date"] < datetime.now().date():
            form.add_error(
                None, "Vergangene Anmeldungen können nicht bearbeitet werden."
            )
            return super().form_invalid(form)
        return super().form_valid(form)

    def get_success_url(self):
        next = self.request.GET.get("next")
        if next == reverse_lazy("my_signups"):
            return next
        return reverse_lazy("trainings")

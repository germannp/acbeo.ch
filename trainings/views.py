import datetime

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import Http404
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
        trainings = Training.objects.filter(
            date__gte=datetime.date.today()
        ).prefetch_related("signups__pilot")
        for training in trainings:
            training.select_signups()
        # Selecting signups can alter their order, but Signup instances cannot be sorted.
        # Refreshing them from the DB is the best solution I found 🤷
        trainings = Training.objects.filter(
            date__gte=datetime.date.today()
        ).prefetch_related("signups__pilot")
        return trainings

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = datetime.date.today()
        context["day_after_tomorrow"] = today + datetime.timedelta(days=2)
        return context


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class TrainingCreateView(StaffRequiredMixin, generic.FormView):
    form_class = forms.TrainingCreateForm
    template_name = "trainings/create_trainings.html"
    success_url = reverse_lazy("trainings")

    def form_valid(self, form):
        form.create_trainings()
        return super().form_valid(form)


class OrgaRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_orga


class TrainingUpdateView(OrgaRequiredMixin, generic.UpdateView):
    form_class = forms.TrainingUpdateForm
    template_name = "trainings/update_training.html"
    success_url = reverse_lazy("trainings")

    def get_object(self):
        if self.kwargs["date"] < datetime.date.today():
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
        today = datetime.date.today()
        if self.kwargs["date"] < today:
            raise Http404(
                "Seepolizeimail kann nicht für vergangene Trainings versandt werden."
            )
        if self.kwargs["date"] > today + datetime.timedelta(days=2):
            raise Http404(
                "Seepolizeimail kann höchstens drei Tage im Voraus versandt werden."
            )
        return get_object_or_404(Training, date=self.kwargs["date"])

    def form_valid(self, form):
        form.sender = self.request.user
        form.send_mail()
        return super().form_valid(form)


class SignupListView(LoginRequiredMixin, generic.ListView):
    context_object_name = "future_and_past_signups"
    template_name = "trainings/list_signups.html"

    def get_queryset(self):
        today = datetime.date.today()
        future_signups = (
            Signup.objects.filter(pilot=self.request.user)
            .filter(training__date__gte=today)
            .select_related("training")
            .prefetch_related("training__signups__pilot")
        )
        for signup in future_signups:
            signup.training.select_signups()
        # After selecting signups, they have to be refreshed from the DB
        signups = (
            Signup.objects.filter(pilot=self.request.user)
            .order_by("training__date")
            .select_related("training")
            .prefetch_related("training__signups")
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
            return context

        today = datetime.date.today()
        if today.weekday() >= 5:  # Saturdays and Sundays
            context["date"] = today
            return context

        next_saturday = today + datetime.timedelta(days=(5 - today.weekday()) % 7)
        context["date"] = next_saturday
        return context

    def form_valid(self, form):
        """Fill in training and pilot"""
        self.date = form.cleaned_data["date"]
        if Training.objects.filter(date=self.date).exists():
            training = Training.objects.get(date=self.date)
        else:
            wednesday_before = self.date + datetime.timedelta(
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

    def get_cancel_url(self):
        cancel_url = reverse_lazy("trainings")
        if page := self.request.GET.get("page"):
            cancel_url += f"?page={page}"
        if training := self.request.GET.get("training"):
            cancel_url += f"#training_{training}"
        return cancel_url

    def get_success_url(self):
        self.success_message = f"Eingeschrieben für {self.date}."
        next_day = self.date + datetime.timedelta(days=1)
        success_url = reverse_lazy("signup", kwargs={"date": next_day})
        if page := self.request.GET.get("page"):
            success_url += f"?page={page}"
        if training := self.request.GET.get("training"):
            success_url += f"&training={training}"
        return success_url


class SignupUpdateView(LoginRequiredMixin, generic.UpdateView):
    form_class = forms.SignupUpdateForm
    template_name = "trainings/update_signup.html"

    def get_object(self):
        if self.kwargs["date"] < datetime.date.today():
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
        if (success_url := self.request.GET.get("next")) == reverse_lazy("my_signups"):
            return success_url

        success_url = reverse_lazy("trainings")
        if page := self.request.GET.get("page"):
            success_url += f"?page={page}"
        if training := self.request.GET.get("training"):
            success_url += f"#training_{training}"
        return success_url

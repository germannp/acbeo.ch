from datetime import date, timedelta
import locale

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import generic

from . import forms
from .models import Signup, Training

locale.setlocale(locale.LC_TIME, "de_CH")


class TrainingListView(LoginRequiredMixin, generic.ListView):
    paginate_by = 4

    def get_queryset(self):
        trainings = Training.objects.filter(date__gte=date.today()).prefetch_related(
            "signups__pilot"
        )
        for training in trainings:
            training.select_signups()
        # Selecting signups can alter their order, but Signup instances cannot be sorted.
        # Refreshing them from the DB is the best solution I found 🤷
        trainings = Training.objects.filter(date__gte=date.today()).prefetch_related(
            "signups__pilot"
        )
        return trainings

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
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
        if self.kwargs["date"] < date.today():
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
        today = date.today()
        if self.kwargs["date"] < today:
            raise Http404(
                "Seepolizeimail kann nicht für vergangene Trainings versandt werden."
            )
        if self.kwargs["date"] > today + timedelta(days=2):
            raise Http404(
                "Seepolizeimail kann höchstens drei Tage im Voraus versandt werden."
            )
        return get_object_or_404(Training, date=self.kwargs["date"])

    def form_valid(self, form):
        form.sender = self.request.user
        form.send_mail()
        return super().form_valid(form)


class SignupListView(LoginRequiredMixin, generic.ListView):
    model = Signup

    def get_queryset(self):
        today = date.today()
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

        today = date.today()
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
                f"Du bist für <b>{self.date.strftime('%A')}</b>, den"
                f"{self.date.strftime(' %d. %B %Y').replace (' 0', ' ')}, bereits eingeschrieben.",
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
            f"Eingeschrieben für <b>{self.date.strftime('%A')}</b>, "
            f"den {self.date.strftime('%d. %B %Y')}.".replace(" 0", " ")
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
        if self.kwargs["date"] < date.today():
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

from datetime import datetime, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views import generic

from .models import Singup
from .forms import SignupForm, UpdateForm


class SingupListView(LoginRequiredMixin, generic.ListView):
    context_object_name = "singups"
    queryset = Singup.objects.filter(date__gte=datetime.now())
    template_name = "trainings/list.html"


class SignupCreateView(LoginRequiredMixin, SuccessMessageMixin, generic.CreateView):
    form_class = SignupForm
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
        self.date = form.instance.date
        today = datetime.now().date()
        if self.date < today:
            form.add_error(
                "date", f"Einschreiben ist nur für zukünftige Trainings möglich."
            )
            return super().form_invalid(form)
        if self.date > today + timedelta(days=365):
            form.add_error(
                "date", f"Einschreiben ist höchstens ein Jahr im Voraus möglich."
            )
            return super().form_invalid(form)
        self.pilot = self.request.user
        if Singup.objects.filter(pilot=self.pilot, date=self.date).exists():
            form.add_error("date", f"Du bist für {self.date} bereits eingeschrieben.")
            return super().form_invalid(form)
        form.instance.pilot = self.pilot
        return super().form_valid(form)

    def get_success_url(self):
        self.success_message =  f"Eingeschrieben für {self.date}."
        next_day = self.date + timedelta(days=1)
        return reverse_lazy("signup", kwargs={"date": next_day})


class SignupUpdateView(LoginRequiredMixin, generic.UpdateView):
    form_class = UpdateForm
    template_name = "trainings/update.html"
    success_url = reverse_lazy("trainings")

    def get_object(self):
        date = self.kwargs["date"]
        pilot = self.request.user
        return get_object_or_404(Singup.objects, pilot=pilot, date=date)

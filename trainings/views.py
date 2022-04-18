from datetime import datetime, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.views import generic

from . import models, forms


class SignupView(LoginRequiredMixin, generic.CreateView):
    form_class = forms.SignupForm
    success_url = "/trainings/"
    template_name = "trainings/signup.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "date" in self.kwargs:
            context["date"] = self.kwargs["date"]
        else:
            today = datetime.now().date()
            next_saturday = today + timedelta(days=(5 - today.weekday()) % 7)
            context["date"] = next_saturday
        return context

    def form_valid(self, form):
        date = form.instance.date
        if date > (datetime.now() + timedelta(days=365)).date():
            form.add_error("date", f"Einschreiben ist nur ein Jahr im voraus möglich.")
            return super().form_invalid(form)
        pilot = self.request.user
        if models.Registration.objects.filter(pilot=pilot, date=date).exists():
            form.add_error("date", f"Du bist für {date} bereits eingeschrieben.")
            return super().form_invalid(form)
        form.instance.pilot = pilot
        return super().form_valid(form)


class UpdateView(LoginRequiredMixin, generic.UpdateView):
    form_class = forms.UpdateForm
    template_name = "trainings/update.html"
    success_url = "/trainings/"

    def get_object(self):
        date = self.kwargs["date"]
        pilot = self.request.user
        return get_object_or_404(models.Registration.objects, pilot=pilot, date=date)


class RegistrationListView(LoginRequiredMixin, generic.ListView):
    context_object_name = "registrations"
    queryset = models.Registration.objects.filter(date__gte=datetime.now())
    template_name = "trainings/list.html"

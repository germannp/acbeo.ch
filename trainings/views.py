from datetime import datetime, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import generic

from .forms import SignupForm
from .models import Registration


class SignupView(LoginRequiredMixin, generic.CreateView):
    form_class = SignupForm
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
        if Registration.objects.filter(pilot=pilot, date=date).exists():
            form.add_error("date", f"Du bist für {date} bereits eingeschrieben.")
            return super().form_invalid(form)
        form.instance.pilot = pilot
        return super().form_valid(form)


class RegistrationListView(LoginRequiredMixin, generic.ListView):
    context_object_name = "registrations"
    queryset = Registration.objects.filter(date__gte=datetime.now())
    template_name = "trainings/list.html"

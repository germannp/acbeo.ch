from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import generic

from .models import Training, Signup
from .forms import TrainingUpdateForm, SignupCreateForm, SignupUpdateForm


class TrainingListView(LoginRequiredMixin, generic.ListView):
    context_object_name = "trainings"
    queryset = Training.objects.filter(date__gte=datetime.now())
    paginate_by = 3
    template_name = "trainings/list_trainings.html"


class TrainingUpdateView(LoginRequiredMixin, generic.UpdateView):
    form_class = TrainingUpdateForm
    template_name = "trainings/update_training.html"
    success_url = reverse_lazy("trainings")

    def get_object(self):
        return get_object_or_404(Training.objects, date=self.kwargs["date"])


class SignupCreateView(LoginRequiredMixin, SuccessMessageMixin, generic.CreateView):
    form_class = SignupCreateForm
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
            form.add_error(
                "date", f"Einschreiben ist nur für zukünftige Trainings möglich."
            )
            return super().form_invalid(form)
        if self.date > today + timedelta(days=365):
            form.add_error(
                "date", f"Einschreiben ist höchstens ein Jahr im Voraus möglich."
            )
            return super().form_invalid(form)
        if Training.objects.filter(date=self.date).exists():
            training = Training.objects.get(date=self.date)
        else:
            training = Training(date=self.date)
            training.save()
        pilot = self.request.user
        if Signup.objects.filter(pilot=pilot, training=training).exists():
            form.add_error("date", f"Du bist für {self.date} bereits eingeschrieben.")
            return super().form_invalid(form)
        form.instance.pilot = pilot
        form.instance.training = training
        return super().form_valid(form)

    def get_success_url(self):
        self.success_message = f"Eingeschrieben für {self.date}."
        next_day = self.date + timedelta(days=1)
        return reverse_lazy("signup", kwargs={"date": next_day})


class SignupUpdateView(LoginRequiredMixin, generic.UpdateView):
    form_class = SignupUpdateForm
    template_name = "trainings/update_signup.html"
    success_url = reverse_lazy("trainings")

    def get_object(self):
        pilot = self.request.user
        training = get_object_or_404(Training, date=self.kwargs["date"])
        signup = get_object_or_404(Signup.objects, pilot=pilot, training=training)
        if "cancel" in self.request.POST:
            signup.cancel()
        elif "resignup" in self.request.POST:
            signup.resignup()
        return signup

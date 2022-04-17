from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import generic

from .models import Registration


class RegistrationList(LoginRequiredMixin, generic.ListView):
    context_object_name = "registrations"
    queryset = Registration.objects.all()
    template_name = "trainings/list.html"

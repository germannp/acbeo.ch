from django.views import generic

from .models import Registration


class RegistrationList(generic.ListView):
    queryset = Registration.objects.all()
    paginate_by = 10
    template_name = "trainings/list.html"

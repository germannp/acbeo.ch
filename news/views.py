from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views import generic

from .forms import ContactForm, PilotCreationForm
from .models import Post


class PostListView(generic.ListView):
    context_object_name = "posts"
    queryset = Post.objects.all()
    paginate_by = 3
    template_name = "news/index.html"


class PostDetailView(generic.DetailView):
    model = Post
    template_name = "news/post.html"


class ContactFormView(SuccessMessageMixin, generic.FormView):
    form_class = ContactForm
    template_name = "news/contact.html"
    success_url = reverse_lazy("home")
    success_message = "Nachricht abgesendet."

    def form_valid(self, form):
        form.send_mail()
        return super().form_valid(form)


class PilotCreateView(SuccessMessageMixin, generic.CreateView):
    form_class = PilotCreationForm
    template_name = "news/register.html"
    success_url = reverse_lazy("login")
    success_message = "Konto angelegt."

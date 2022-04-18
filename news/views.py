from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views import generic

from .forms import UserCreationForm
from .models import Post


class RegistrationView(SuccessMessageMixin, generic.CreateView):
    form_class = UserCreationForm
    template_name = "news/register.html"
    success_url = reverse_lazy("login")
    success_message = "Konto angelegt."


class PostListView(generic.ListView):
    context_object_name = "posts"
    queryset = Post.objects.all().order_by("-created_on")
    paginate_by = 3
    template_name = "news/index.html"


class PostDetailView(generic.DetailView):
    model = Post
    template_name = "news/post.html"

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views import generic

from .forms import ContactForm, MembershipForm, PilotCreationForm
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


class NonMemberOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return not self.request.user.is_member


class MembershipFormView(NonMemberOnlyMixin, SuccessMessageMixin, generic.FormView):
    form_class = MembershipForm
    template_name = "news/membership.html"
    success_url = reverse_lazy("home")
    success_message = "Mitgliedschaft beantragt."

    def form_valid(self, form):
        form.sender = self.request.user
        form.send_mail()
        self.request.user.make_member()
        return super().form_valid(form)

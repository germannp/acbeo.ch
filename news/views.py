from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views import generic

from .forms import ContactForm, MembershipForm, PilotCreationForm, PilotUpdateForm
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

    def get_initial(self):
        initial = super(ContactFormView, self).get_initial()
        if self.request.user.is_authenticated:
            initial["email"] = self.request.user.email
        if subject := self.request.GET.get("subject"):
            initial["subject"] = subject
        return initial

    def form_valid(self, form):
        form.send_mail()
        return super().form_valid(form)


class LoginForbiddenMixin(UserPassesTestMixin):
    def test_func(self):
        return not self.request.user.is_authenticated


class PilotCreateView(LoginForbiddenMixin, SuccessMessageMixin, generic.CreateView):
    form_class = PilotCreationForm
    template_name = "news/register.html"
    success_message = "Konto angelegt."

    def get_success_url(self):
        success_url = reverse_lazy("login")
        if next := self.request.GET.get("next"):
            success_url += f"?next={next}"
        return success_url


class PilotUpdateView(LoginRequiredMixin, SuccessMessageMixin, generic.UpdateView):
    form_class = PilotUpdateForm
    template_name = "news/update_pilot.html"
    success_message = "Änderungen gespeichert."

    def get_object(self):
        return self.request.user

    def form_valid(self, form):
        if self.request.user.is_member:
            form.send_mail()
        return super().form_valid(form)

    def get_success_url(self):
        if success_url := self.request.GET.get("next"):
            return success_url
        return reverse_lazy("home")


class PilotPasswordResetView(SuccessMessageMixin, PasswordResetView):
    template_name = "news/password_reset.html"
    subject_template_name = "news/password_reset_subject.txt"
    email_template_name = "news/password_reset_email.html"
    success_url = reverse_lazy("home")
    success_message = (
        "Instruktionen zum Zurücksetzen des Passworts wurden an die angegebene Email "
        "geschickt."
    )


class PilotPasswordResetConfirmView(SuccessMessageMixin, PasswordResetConfirmView):
    template_name = "news/password_reset_confirm.html"
    success_url = reverse_lazy("login")
    success_message = "Passwort geändert."


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

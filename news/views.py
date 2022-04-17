from django.views import generic

from .models import Post


class PostList(generic.ListView):
    context_object_name = "posts"
    queryset = Post.objects.all().order_by("-created_on")
    paginate_by = 3
    template_name = "news/index.html"


class PostDetail(generic.DetailView):
    model = Post
    template_name = "news/post.html"

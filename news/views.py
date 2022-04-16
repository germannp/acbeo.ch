from django.views import generic

from .models import Post


class PostList(generic.ListView):
    queryset = Post.objects.all().order_by("-created_on")
    paginate_by = 4
    template_name = "news/index.html"


class PostDetail(generic.DetailView):
    model = Post
    template_name = "news/post.html"

from django.http import HttpResponsePermanentRedirect


class RedirectToNonWwwMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        host = request.META.get("HTTP_HOST")

        if host and host.startswith("www."):
            non_www = host.replace("www.", "")
            return HttpResponsePermanentRedirect("https://" + non_www + request.path)

        return response

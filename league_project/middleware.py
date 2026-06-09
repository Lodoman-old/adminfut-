import re
from django.conf import settings

NGROK_RE = re.compile(r'^https://[a-zA-Z0-9.-]+\.ngrok-free\.(app|dev)$')


class AutoNgrokCSRFMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.META.get('HTTP_ORIGIN', '')
        if origin and origin not in settings.CSRF_TRUSTED_ORIGINS and NGROK_RE.match(origin):
            settings.CSRF_TRUSTED_ORIGINS.append(origin)
        return self.get_response(request)

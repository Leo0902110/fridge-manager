"""WSGI config for Django service."""

import os

from django.core.wsgi import get_wsgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fridge_service.settings")

application = get_wsgi_application()
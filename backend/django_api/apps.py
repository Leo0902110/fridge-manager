from django.apps import AppConfig


class DjangoApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_api"

    def ready(self):
        from .bootstrap import ensure_legacy_schema

        ensure_legacy_schema()
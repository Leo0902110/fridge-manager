"""Root URL config for Django service."""

from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from django_api.views_common import health_check, root_view


urlpatterns = [
    path("", root_view, name="root"),
    path("health", health_check, name="health"),
    path("api/v1/", include("django_api.urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
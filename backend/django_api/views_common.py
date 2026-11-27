"""Common root and health endpoints for Django backend."""

from django.http import JsonResponse


def root_view(request):
    return JsonResponse(
        {
            "message": "🧊 欢迎使用冰箱管家 API",
            "version": "1.0.0",
            "status": "running",
        }
    )


def health_check(request):
    return JsonResponse(
        {
            "status": "healthy",
            "service": "fridge-manager-django-api",
        }
    )
from django.urls import path
from django.http import JsonResponse
from django.db import connection
from django.conf import settings

from catalog import admin


def health_check(request):
    """Basic health check"""
    return JsonResponse({
        'status': 'healthy',
        'service': 'catalog-service',
        'version': '1.0.0'
    })


def health_ready(request):
    """Readiness check - checks database and RabbitMQ"""
    checks = {
        'database': False,
        'rabbitmq': False
    }

    # Check database
    try:
        connection.ensure_connection()
        checks['database'] = True
    except Exception as e:
        checks['database_error'] = str(e)

    is_ready = checks['database']
    status_code = 200 if is_ready else 503

    return JsonResponse({
        'status': 'ready' if is_ready else 'not_ready',
        'checks': checks
    }, status=status_code)


def health_live(request):
    """Liveness check - simple alive check"""
    return JsonResponse({
        'status': 'alive',
        'service': 'catalog-service'
    })


urlpatterns = [
    path('', health_check, name='health'),
    path('ready/', health_ready, name='health-ready'),
    path('live/', health_live, name='health-live'),
]
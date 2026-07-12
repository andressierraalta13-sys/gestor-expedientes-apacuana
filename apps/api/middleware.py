"""
Middlewares de Seguridad — Sistema de Gestión APACUANA
=======================================================
1. BlockDeleteMiddleware       → Bloquea métodos DELETE en rutas /api/* y retorna 403 JSON.
2. JsonErrorMiddleware         → Intercepta errores 500/404 en rutas /api/* y retorna JSON.
3. SanitizeInputMiddleware     → Sanitiza inputs POST/PUT/PATCH contra XSS básico.
4. RequestTelemetryMiddleware  → Captura métricas de cada request para el panel de observabilidad.

"""

import json
import logging
import re
import time

from django.http import JsonResponse
from django.utils.timezone import now
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Rutas protegidas por los middlewares (prefix matching)
_API_PREFIXES = ('/api/', '/pagos/api/', '/horarios/api/', '/ia/')

# ─── Configuración de telemetría ──────────────────────────────────────────────
_TELEMETRY_WINDOW_MINUTES = 60   # ventana de retención
_TELEMETRY_BUCKET_KEY = 'dev_telemetry_bucket:{}'   # clave por minuto
_TELEMETRY_INDEX_KEY  = 'dev_telemetry_index'       # índice de buckets activos


class RequestTelemetryMiddleware:
    """
    Captura métricas de cada petición HTTP para el panel de observabilidad
    del desarrollador. Almacena datos en cache con ventana deslizante de 60 min.

    Datos capturados por request:
      - timestamp (epoch float)
      - método HTTP
      - path
      - status_code
      - latencia_ms (tiempo total de respuesta)
      - ip
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        t0 = time.monotonic()
        response = self.get_response(request)
        latencia_ms = round((time.monotonic() - t0) * 1000, 2)

        try:
            from django.utils import timezone
            import datetime

            ts_now   = timezone.now()
            # Clave por minuto → bucket de 60 segundos
            bucket   = ts_now.strftime('%Y%m%d%H%M')
            cache_key = _TELEMETRY_BUCKET_KEY.format(bucket)

            entry = {
                'ts':          ts_now.timestamp(),
                'method':      request.method,
                'path':        request.path[:120],
                'status':      response.status_code,
                'latencia_ms': latencia_ms,
                'ip':          (
                    request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
                    or request.META.get('REMOTE_ADDR', '?')
                ),
            }

            # Obtener bucket actual o crear nuevo
            bucket_data = cache.get(cache_key, [])
            bucket_data.append(entry)
            # TTL = ventana + 5 min de margen
            cache.set(cache_key, bucket_data, timeout=(_TELEMETRY_WINDOW_MINUTES + 5) * 60)

            # Actualizar índice de buckets activos
            index = cache.get(_TELEMETRY_INDEX_KEY, [])
            if bucket not in index:
                index.append(bucket)
                # Mantener solo los últimos N buckets
                if len(index) > _TELEMETRY_WINDOW_MINUTES + 5:
                    index = index[-(  _TELEMETRY_WINDOW_MINUTES + 5):]
                cache.set(_TELEMETRY_INDEX_KEY, index, timeout=(_TELEMETRY_WINDOW_MINUTES + 10) * 60)

        except Exception:
            pass  # Nunca interrumpir el flujo por telemetría

        return response




def _is_api_route(path: str) -> bool:
    return any(path.startswith(p) for p in _API_PREFIXES)


def _strip_xss(value: str) -> str:
    """Elimina tags HTML básicos para prevenir XSS en campos de texto."""
    # Remover tags HTML
    clean = re.sub(r'<[^>]+>', '', str(value))
    # Escapar secuencias peligrosas de JS
    clean = clean.replace('javascript:', '').replace('onload=', '').replace('onerror=', '')
    return clean.strip()


class BlockDeleteMiddleware:
    """
    Intercepta peticiones HTTP DELETE a rutas de API y las bloquea
    retornando 403 JSON con registro de auditoría.
    Parámetro inmutable del sistema: ELIMINACIÓN PROHIBIDA.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'DELETE' and _is_api_route(request.path):
            usuario = str(request.user) if hasattr(request, 'user') and request.user.is_authenticated else 'Anónimo'
            logger.warning(
                f"[SEGURIDAD] Intento de DELETE bloqueado — ruta: {request.path} — usuario: {usuario} — IP: {request.META.get('REMOTE_ADDR', '?')}"
            )
            # Registrar en auditoría si el modelo está disponible
            try:
                from auditoria.models import registrar_evento
                registrar_evento(
                    tipo='BLOQUEO_DELETE',
                    descripcion=f"Intento de eliminación bloqueado en {request.path}",
                    modulo=request.path,
                    usuario=usuario,
                    nivel_riesgo='CRITICO',
                    exitoso=False,
                )
            except Exception:
                pass  # No interrumpir si la auditoría falla

            return JsonResponse({
                'error': 'Operación no permitida.',
                'detalle': 'La eliminación de datos está estrictamente prohibida por el marco de gobernanza del sistema. '
                           'Para desactivar un registro, utilice la opción de inactivación.',
                'codigo': 'DELETE_FORBIDDEN',
            }, status=403)

        return self.get_response(request)


class JsonErrorMiddleware:
    """
    Intercepta errores 500/404 en rutas de API y los convierte a
    respuestas JSON estructuradas en lugar de páginas HTML de error.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if _is_api_route(request.path):
            if response.status_code == 404 and 'text/html' in response.get('Content-Type', ''):
                return JsonResponse({
                    'error': 'Recurso no encontrado.',
                    'ruta': request.path,
                    'codigo': 'NOT_FOUND',
                }, status=404)

            if response.status_code == 500 and 'text/html' in response.get('Content-Type', ''):
                logger.error(f"[API 500] Respuesta HTML en ruta API — {request.path}")
                return JsonResponse({
                    'error': 'Error interno del servidor.',
                    'detalle': 'Se ha producido un error inesperado. El incidente fue registrado.',
                    'codigo': 'INTERNAL_ERROR',
                }, status=500)

        return response

    def process_exception(self, request, exception):
        """Captura excepciones no controladas en rutas API."""
        if _is_api_route(request.path):
            logger.error(
                f"[API EXCEPTION] {type(exception).__name__}: {exception} — ruta: {request.path}",
                exc_info=True
            )
            return JsonResponse({
                'error': 'Error inesperado en el servidor.',
                'tipo': type(exception).__name__,
                'detalle': str(exception),
                'codigo': 'UNHANDLED_EXCEPTION',
            }, status=500)
        return None


class SanitizeInputMiddleware:
    """
    Sanitiza campos de texto en peticiones POST/PUT/PATCH para
    prevenir inyecciones XSS básicas en la interfaz.
    Solo afecta a content-type application/x-www-form-urlencoded
    (formularios HTML). Las APIs JSON se sanitizan en el serializer.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ('POST', 'PUT', 'PATCH'):
            content_type = request.META.get('CONTENT_TYPE', '')
            # Solo sanitizar formularios HTML (no JSON de API)
            if 'application/x-www-form-urlencoded' in content_type or 'multipart/form-data' in content_type:
                try:
                    mutable = request.POST.copy()
                    for key in mutable:
                        if isinstance(mutable[key], str):
                            mutable[key] = _strip_xss(mutable[key])
                    request.POST = mutable
                except Exception:
                    pass  # Nunca interrumpir el flujo por sanitización

        return self.get_response(request)


class RequireLoginMiddleware:
    """
    Middleware de Seguridad Estricta:
    Obliga a todos los usuarios a iniciar sesión para acceder a CUALQUIER URL,
    excepto a la vista de login y archivos estáticos/media.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Rutas exentas de requerir inicio de sesión
        exempt_routes = [
            '/login/',
            '/admin/',  # admin de django tiene su propio login
            '/static/',
            '/media/',
        ]

        is_exempt = any(request.path.startswith(route) for route in exempt_routes)

        if not request.user.is_authenticated and not is_exempt:
            from django.shortcuts import redirect
            from django.conf import settings
            import urllib.parse
            
            # Guardamos la URL a la que quería acceder para redirigirlo después (opcional)
            path = request.path
            return redirect(f"{settings.LOGIN_URL}?next={urllib.parse.quote(path)}")

        return self.get_response(request)

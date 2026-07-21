"""
Django settings for GestorExpedientes APACUANA.

Configurado para producción en Render.com con Supabase (PostgreSQL)
y Upstash Redis. Compatible con Python 3.12 y Django 6.0.4.
"""

import os
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, os.path.join(BASE_DIR, 'apps'))


# ── Forzar IPv4 Globalmente para requests (Vercel Serverless IPv6 Fix) ──────
import socket
try:
    import urllib3.util.connection as urllib3_cn
    def allowed_gai_family():
        return socket.AF_INET
    urllib3_cn.allowed_gai_family = allowed_gai_family
except ImportError:
    pass


# ── Seguridad ─────────────────────────────────────────────────────────────────
# NUNCA hardcodear el secret key en producción. Usar variable de entorno.
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-(#9ti)xbors=(jc29oheg7&^ub*^1hdf5j)mwe2@dnhpvsdk^_'  # Solo para dev local
)

DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# ALLOWED_HOSTS dinámico: acepta lista desde entorno + host de Render
_raw_hosts = os.environ.get('ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(',') if h.strip()]

# Garantizar localhost y 127.0.0.1 en ALLOWED_HOSTS
for host in ['localhost', '127.0.0.1']:
    if host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)

# ── CSRF_TRUSTED_ORIGINS ──────────────────────────────────────────────────────
# Dominios desde los cuales Django acepta POST (formularios con CSRF token).
CSRF_TRUSTED_ORIGINS = [
    'https://gestor-apacuana.vercel.app',
    'https://*.vercel.app',
    'http://localhost',
    'http://127.0.0.1',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# ── NUEVO: Soporte automático y seguro para GitHub Codespaces ──
# Detecta si estás en Codespaces y permite su dominio sin afectar producción (Render)
if os.environ.get('CODESPACES') == 'true':
    ALLOWED_HOSTS.extend(['.app.github.dev'])
    CSRF_TRUSTED_ORIGINS.append('https://*.app.github.dev')

if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ['*']

# Render inyecta RENDER_EXTERNAL_HOSTNAME automáticamente (*.onrender.com)
_render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')
if _render_host and _render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_host)


# ── Aplicaciones ──────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-Party Apps
    'simple_history',
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'django_celery_results',

    # Almacenamiento en la nube
    'cloudinary_storage',
    'cloudinary',

    # Local Apps
    'usuarios',
    'api',
    'estudiantes',
    'inscripciones',
    'calificaciones',
    'graduacion',
    'auditoria',
    'asistencias',
    'ia_analitica',
    'pagos',
    'horarios',
    'docentes',
]


# ── Middleware ─────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise DEBE ir inmediatamente despues de SecurityMiddleware
    'whitenoise.middleware.WhiteNoiseMiddleware',
    # ── Telemetría de Observabilidad (antes de todo para capturar tiempos reales)
    'api.middleware.RequestTelemetryMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
    # ── Middlewares de Seguridad APACUANA ─────────────────────────────────────
    'api.middleware.RequireLoginMiddleware',   # Fuerza autenticación global
    'api.middleware.BlockDeleteMiddleware',    # Bloquea DELETE en /api/*
    'api.middleware.JsonErrorMiddleware',      # JSON en lugar de HTML 500/404
    'api.middleware.SanitizeInputMiddleware',  # Sanitizacion XSS en formularios
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# ── Base de Datos ─────────────────────────────────────────────────────────────
# Lee DATABASE_URL del entorno (Supabase/PostgreSQL en produccion).
# Si no existe, usa SQLite para desarrollo local.
_database_url = os.environ.get('DATABASE_URL', '')

if _database_url:
    import urllib.parse as _up
    import socket

    _parsed = _up.urlparse(_database_url)

    _db_host = _parsed.hostname
    _db_user = _parsed.username

    # ── Resolución forzada a IPv4 (Solo para hosts que no sean el Pooler) ────────
    # Vercel Serverless no soporta conexiones salientes IPv6.
    # Si es el pooler (contiene 'pooler.supabase.com'), ya tiene IPv4 de forma nativa.
    # Si es la conexión directa (db.xxx.supabase.co), intentamos resolver a IPv4
    # (aunque las bases de datos gratis de Supabase son IPv6-only y fallará, forzando a usar el Pooler).
    if _db_host and "pooler.supabase.com" not in _db_host:
        try:
            _ipv4_results = socket.getaddrinfo(_db_host, _parsed.port or 5432, socket.AF_INET)
            if _ipv4_results:
                _db_host = _ipv4_results[0][4][0]  # Usar la primera dirección IPv4
        except Exception:
            pass  # Si falla, usar el hostname original

    # Configuración de opciones SSL obligatorias
    _db_options = {
        'sslmode': 'require',
    }

    # Si se usa la conexión directa (el usuario es 'postgres' sin el ref del proyecto),
    # pasamos el parámetro de proyecto en las opciones. Si se usa el pooler
    # (el usuario es 'postgres.ref'), no se debe enviar 'options' para evitar conflictos.
    if _db_user and '.' not in _db_user:
        _db_options['options'] = '-c project=vgzojsbmmvptfhdrfsko'

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': _parsed.path.lstrip('/'),
            'USER': _db_user,
            'PASSWORD': _up.unquote(_parsed.password) if _parsed.password else '',
            'HOST': _db_host,
            'PORT': _parsed.port or 5432,
            'CONN_MAX_AGE': 600,        # Reutilizar conexiones por 10 minutos
            'OPTIONS': _db_options,
        }
    }
else:
    # Desarrollo local: SQLite sin configuracion adicional
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# ── Validadores de Contrasena ─────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ── Internacionalizacion ───────────────────────────────────────────────────────
LANGUAGE_CODE = 'es-ve'
TIME_ZONE = 'America/Caracas'
USE_I18N = True
USE_TZ = True


# ── Archivos Estaticos (WhiteNoise) ───────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Configuración de Cloudinary para archivos multimedia
_cloudinary_url = os.environ.get('CLOUDINARY_URL')
_cloudinary_secret = os.environ.get('CLOUDINARY_API_SECRET')

# Si el usuario configuró CLOUDINARY_URL (incluso si cometió el error de pegar "CLOUDINARY_URL=" en el valor)
if _cloudinary_url:
    # Corrección automática si el usuario pegó el "CLOUDINARY_URL=" dentro del valor
    if _cloudinary_url.startswith('CLOUDINARY_URL='):
        _cloudinary_url = _cloudinary_url.replace('CLOUDINARY_URL=', '')
        os.environ['CLOUDINARY_URL'] = _cloudinary_url

    STORAGES["default"]["BACKEND"] = 'cloudinary_storage.storage.MediaCloudinaryStorage'
elif _cloudinary_secret:
    CLOUDINARY_STORAGE = {
        'CLOUD_NAME': 'dt1yf41jb',
        'API_KEY': '139114295273585',
        'API_SECRET': _cloudinary_secret,
    }
    STORAGES["default"]["BACKEND"] = 'cloudinary_storage.storage.MediaCloudinaryStorage'


# ── Modelo de Usuario Personalizado ───────────────────────────────────────────
AUTH_USER_MODEL = 'usuarios.Usuario'


# ── Email ──────────────────────────────────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'notificaciones@colegioapacuana.edu.ve'


# ── Django REST Framework ──────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day',
        'ia':   '30/hour',
    },
}


# ── DRF Spectacular (Swagger) ──────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'API Gestor de Expedientes',
    'DESCRIPTION': 'Documentacion de las APIs del sistema universitario.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}


# ── Celery + Redis (Upstash con SSL) ──────────────────────────────────────────
# REDIS_URL debe ser rediss:// (doble s) para Upstash TLS
_redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

_redis_ssl_options = {}
if _redis_url.startswith('rediss://'):
    # SSL habilitado: Upstash no requiere verificar certificado del cliente
    CELERY_BROKER_USE_SSL = {'ssl_cert_reqs': 'CERT_NONE'}
    CELERY_REDIS_BACKEND_USE_SSL = {'ssl_cert_reqs': 'CERT_NONE'}
    _redis_ssl_options = {'ssl_cert_reqs': None}

CELERY_BROKER_URL = _redis_url
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_BACKEND = 'django-db'    # Resultados en la BD de Django (Supabase)
CELERY_CACHE_BACKEND = 'django-cache'


# ── Caché Global (Detección dinámica y fallback inteligente para dev local) ───
# En desarrollo local (DEBUG=True), si Redis no está activo en localhost:6379,
# hacemos fallback a LocMemCache (caché en memoria interna) para evitar caídas del sitio.
_use_redis_cache = True
if DEBUG and _redis_url.startswith('redis://localhost:6379'):
    import socket
    try:
        _s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _s.settimeout(0.5)  # Timeout rápido de medio segundo
        _s.connect(('127.0.0.1', 6379))
        _s.close()
    except Exception:
        _use_redis_cache = False

if _use_redis_cache:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': _redis_url,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'IGNORE_EXCEPTIONS': True,  # Evita que caiga el sitio si hay una microcaída de Redis
                'CONNECTION_POOL_KWARGS': {
                    'socket_connect_timeout': 2,
                    'socket_timeout': 2,
                    **({'ssl_cert_reqs': None} if _redis_ssl_options else {})
                },
            },
            'KEY_PREFIX': 'apacuana',
            'TIMEOUT': 3600,  # TTL por defecto: 1 hora
        }
    }
else:
    # Fallback elegante a la caché en memoria integrada de Django si Redis está inactivo
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'apacuana-local-fallback',
            'KEY_PREFIX': 'apacuana',
            'TIMEOUT': 3600,
        }
    }

# Usar cached_db para las sesiones. 
# Si Redis falla (ej. sin configurar), usa la DB automáticamente para que nadie pierda acceso.
# Si la DB falla, mantiene la sesión viva desde Redis.
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 43200  # 12 horas
SESSION_EXPIRE_AT_BROWSER_CLOSE = True


# ── Integraciones Externas ─────────────────────────────────────────────────────
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')

# Supabase (para uso directo desde Python/JS si es necesario)
# .strip() elimina espacios/saltos de línea accidentales al pegar en Vercel
SUPABASE_URL = os.environ.get('SUPABASE_URL', '').strip()
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY', '').strip()
SUPABASE_SERVICE_ROLE_KEY = (
    os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or 
    os.environ.get('SUPABASE_SERVICE_KEY') or 
    os.environ.get('SERVICE_ROLE_KEY') or 
    os.environ.get('SUPABASE_SECRET_KEY') or 
    ''
).strip()



# ── Autenticacion ──────────────────────────────────────────────────────────────
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'


# ── Seguridad en Produccion ────────────────────────────────────────────────────
# Solo activo cuando DEBUG=False
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000          # 1 anno
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
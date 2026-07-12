import os
from celery import Celery

# Establece el módulo de configuración de Django ('config' asumiendo el nombre de tu proyecto)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('gestor_expedientes')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

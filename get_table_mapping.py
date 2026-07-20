import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.apps import apps
import json

mapping = {}
for model in apps.get_models():
    mapping[model._meta.label_lower] = model._meta.db_table

print(json.dumps(mapping, indent=2))

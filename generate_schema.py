import os
import sys
import django
from io import StringIO
from django.core.management import call_command
from django.db import connection

# Configurar entorno
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Forzar URL de base de datos a PostgreSQL local o dummy para que use el dialecto de Postgres
os.environ['DATABASE_URL'] = 'postgresql://dummy:dummy@localhost/dummy'

django.setup()

# Mockear ensure_connection para que no intente conectarse de verdad
def dummy_ensure_connection(*args, **kwargs):
    pass

connection.ensure_connection = dummy_ensure_connection
connection.connection = type('DummyConnection', (object,), {'server_version': 130000})()

from django.db.migrations.loader import MigrationLoader

loader = MigrationLoader(None, ignore_no_migrations=True)
graph = loader.graph

# Obtener todos los nodos en orden topologico
nodes = graph.leaf_nodes()
plan = []
for node in nodes:
    for migration in graph.backwards_plan(node):
        if migration not in plan:
            plan.append(migration)

print(f"Encontradas {len(plan)} migraciones.")

with open('schema_postgres.sql', 'w', encoding='utf-8') as f:
    for app_label, name in plan:
        out = StringIO()
        try:
            call_command('sqlmigrate', app_label, name, stdout=out)
            sql = out.getvalue()
            f.write(f"-- MIGRATION: {app_label}.{name}\n")
            f.write(sql)
            f.write('\n\n')
            print(f"Exportada: {app_label}.{name}")
        except Exception as e:
            print(f"Error exportando {app_label}.{name}: {e}")

print("Completado. Guardado en schema_postgres.sql")

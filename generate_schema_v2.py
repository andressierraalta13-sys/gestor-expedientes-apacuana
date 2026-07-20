import os
import sys
from io import StringIO
import django

# Configurar entorno
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Forzar URL de base de datos a PostgreSQL
os.environ['DATABASE_URL'] = 'postgresql://dummy:dummy@localhost/dummy'

django.setup()

# Patch the migration recorder so it doesn't hit the DB!
from django.db.migrations.recorder import MigrationRecorder
MigrationRecorder.applied_migrations = lambda self: set()
MigrationRecorder.has_table = lambda self: False

# Patch connection to return dummy info so base init doesn't fail
from django.db import connection
def dummy_ensure_connection(*args, **kwargs):
    pass
connection.ensure_connection = dummy_ensure_connection

class DummyCursor:
    query = b""
    def execute(self, *args, **kwargs): pass
    def mogrify(self, sql, params=None):
        if isinstance(sql, bytes): sql = sql.decode('utf-8')
        if params:
            formatted_params = []
            for p in params:
                if p is None: formatted_params.append('NULL')
                elif isinstance(p, bool): formatted_params.append('true' if p else 'false')
                elif isinstance(p, (int, float)): formatted_params.append(str(p))
                else: formatted_params.append(f"'{str(p).replace(chr(39), chr(39)+chr(39))}'")
            sql = sql % tuple(formatted_params)
        return sql.encode('utf-8')
    def fetchall(self): return []
    def fetchmany(self, size): return []
    def close(self): pass
    @property
    def rowcount(self): return 1
    def __enter__(self): return self
    def __exit__(self, *args): pass

class DummyConnection:
    server_version = 130000
    features = connection.features
    ops = connection.ops
    
    def cursor(self, *args, **kwargs):
        return DummyCursor()
    def close(self): pass
    def commit(self): pass
    def rollback(self): pass

connection.connection = DummyConnection()

from django.db.migrations.loader import MigrationLoader
from django.core.management import call_command

loader = MigrationLoader(None, ignore_no_migrations=True)
graph = loader.graph

# Build topological order
nodes = loader.graph.nodes.keys()
plan = []
# Create a dummy node that depends on all leaf nodes, then backwards plan
leaf_nodes = loader.graph.leaf_nodes()
for leaf in leaf_nodes:
    for migration in loader.graph.backwards_plan(leaf):
        if migration not in plan:
            plan.append(migration)

# Now reverse to get forward order
plan.reverse()
# but wait! backwards_plan from multiple leaf nodes appending to plan might mess up topological order when reversed!
# Better to use forwards_plan if we can, or just sort topologically.
# Actually, Django has a build-in method to get the full plan:
# Let's get the plan to run ALL unapplied migrations (which is all of them since applied is empty)
targets = loader.graph.leaf_nodes()
from django.db.migrations.executor import MigrationExecutor
executor = MigrationExecutor(connection)
# executor.loader is already initialized and hits the db, so we need to inject our loader
executor.loader = loader
plan_tuples = executor.migration_plan(targets)
plan = [(m.app_label, m.name) for m, b in plan_tuples]

print(f"Encontradas {len(plan)} migraciones.")

with open('schema_postgres.sql', 'w', encoding='utf-8') as f:
    for app_label, name in plan:
        out = StringIO()
        try:
            call_command('sqlmigrate', app_label, name, stdout=out)
            sql = out.getvalue()
            f.write(f"-- MIGRATION: {app_label}.{name}\\n")
            f.write(sql)
            f.write('\\n\\n')
            print(f"Exportada: {app_label}.{name}")
        except Exception as e:
            print(f"Error exportando {app_label}.{name}: {e}")

print("Completado. Guardado en schema_postgres.sql")

import os
import sys
import django
from django.core.management import call_command

# Configurar entorno
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Forzar URL de base de datos a PostgreSQL
os.environ['DATABASE_URL'] = 'postgresql://dummy:dummy@localhost/dummy'

# Patch psycopg connect
import psycopg
class MockCursor:
    def __init__(self):
        pass
    def execute(self, query, vars=None):
        with open('migrate_queries.sql', 'a', encoding='utf-8') as f:
            f.write(f"-- EXECUTE: {query}\\n")
        return self
    def fetchone(self):
        return (None,)
    def fetchall(self):
        return []
    def close(self):
        pass
    def fetchmany(self, size):
        return []
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    @property
    def description(self):
        return []
    @property
    def rowcount(self):
        return 1

class MockConnection:
    def __init__(self):
        self.info = type('Info', (), {'server_version': 130000})()
        self.autocommit = True
    def cursor(self, *args, **kwargs):
        return MockCursor()
    def close(self):
        pass
    def commit(self):
        pass
    def rollback(self):
        pass
    def set_session(self, **kwargs):
        pass
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

def mock_connect(*args, **kwargs):
    return MockConnection()

psycopg.connect = mock_connect

django.setup()

with open('migrate_queries.sql', 'w', encoding='utf-8') as f:
    f.write("-- INICIO DE MIGRACIONES\\n")

print("Ejecutando migrate con mock...")
try:
    call_command('migrate')
except Exception as e:
    print(f"Error: {e}")

print("Terminado.")

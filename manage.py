#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# Cargar variables de entorno desde .env en desarrollo local.
# En produccion (Render) las variables ya estan en el entorno del sistema.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # En produccion no se necesita dotenv


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()

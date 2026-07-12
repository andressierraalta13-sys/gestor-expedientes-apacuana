import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from usuarios.models import Usuario

def create_user(username, password, role, is_staff=False, is_superuser=False):
    if not Usuario.objects.filter(username=username).exists():
        user = Usuario.objects.create_user(
            username=username,
            password=password,
            rol=role,
            is_staff=is_staff,
            is_superuser=is_superuser
        )
        print(f"Usuario {username} creado con rol {role}")
    else:
        print(f"Usuario {username} ya existe")

# Crear el superusuario principal (Director)
create_user('director', 'admin123', 'DIRECTOR', True, True)

# Crear un Administrativo para probar pagos
create_user('admin_pagos', 'admin123', 'ADMINISTRATIVO', True, False)

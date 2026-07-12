from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Crea/actualiza las cuentas principales del sistema APACUANA.'

    def handle(self, *args, **options):
        Usuario = get_user_model()

        # Limpiar usuarios anteriores (opcional, para mantener orden)
        try:
            Usuario.objects.filter(username__in=['whitxblack', 'andressierraalta', 'directora', 'administrativo']).delete()
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Advertencia: No se pudieron eliminar usuarios previos (posible tabla faltante): {e}'))

        usuarios_config = [
            {
                # Cuenta de Directora (username 'directora')
                'username': 'directora',
                'email': 'whitxblack901@gmail.com',
                'nombre_completo': 'Directora',
                'rol': 'ADMINISTRATIVO',
                'is_superuser': True,
                'is_staff': True,
                'password_env': 'ADMIN_PASSWORD',
                'password_default': 'Admin.Apacuana2026',
            },
            {
                # Cuenta de Administrativo / Coordinador Académico (username 'administrativo')
                'username': 'administrativo',
                'email': 'andressierraalta12@gmail.com',
                'nombre_completo': 'Administrativo',
                'rol': 'COORDINADOR',
                'is_superuser': False,
                'is_staff': True,
                'password_env': 'PERSONAL_PASSWORD',
                'password_default': '123456',
            },
            {
                # Cuenta de Desarrollador (OCULTA — solo para mantenimiento técnico)
                'username': 'admin',
                'email': 'andressierraalta13@gmail.com',
                'nombre_completo': 'Desarrollador',
                'rol': 'DESARROLLADOR',
                'is_superuser': True,
                'is_staff': True,
                'password_env': 'DEVELOPER_PASSWORD',
                'password_default': 'admin',
            },
        ]

        for cfg in usuarios_config:
            import os
            password = os.environ.get(cfg['password_env'], cfg['password_default'])

            usuario, creado = Usuario.objects.get_or_create(username=cfg['username'])
            usuario.email = cfg['email']
            usuario.nombre_completo = cfg['nombre_completo']
            usuario.rol = cfg['rol']
            usuario.is_superuser = cfg['is_superuser']
            usuario.is_staff = cfg['is_staff']
            usuario.is_active = True
            usuario.set_password(password)
            usuario.save()

            accion = 'Creado' if creado else 'Actualizado'
            self.stdout.write(
                self.style.SUCCESS(
                    f'[{accion}] {cfg["username"]} | Rol: {cfg["rol"]} | Email: {cfg["email"]}'
                )
            )

        self.stdout.write(self.style.SUCCESS('\nUsuarios del sistema actualizados con éxito.'))

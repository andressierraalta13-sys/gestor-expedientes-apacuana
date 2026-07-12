from django.contrib.auth.models import AbstractUser
from django.db import models
from simple_history.models import HistoricalRecords

class Usuario(AbstractUser):
    class Role(models.TextChoices):
        DESARROLLADOR = 'DESARROLLADOR', 'Desarrollador'
        PERSONAL      = 'PERSONAL',      'ADMINISTRATIVO'
        ADMINISTRATIVO = 'ADMINISTRATIVO', 'DIRECTORA'
        COORDINADOR   = 'COORDINADOR',   'Coordinador Académico'
        DOCENTE       = 'DOCENTE',       'Docente'
        AUDITOR       = 'AUDITOR',       'Auditor'

    rol = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.PERSONAL
    )
    email = models.EmailField(unique=True)
    nombre_completo = models.CharField(
        max_length=200, blank=True, default='',
        help_text='Nombre y apellido del operador para mostrar en el sistema.'
    )

    # Mantiene un registro de auditoría de los cambios (ej. cambios de rol)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.username} - {self.get_rol_display()}"


class PerfilAdministrativo(models.Model):
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    cedula = models.CharField(max_length=20, unique=True, null=True, blank=True)
    cargo = models.CharField(max_length=150)
    telefono = models.CharField(max_length=20)
    email = models.EmailField()
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Perfil de {self.nombres} {self.apellidos}"

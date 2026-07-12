from django.db import models
from usuarios.models import Usuario

class RegistroAsistencia(models.Model):
    TIPO_CHOICES = (
        ('PERSONAL', 'Personal Administrativo'),
        ('ESTUDIANTE', 'Estudiante'),
    )
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES)
    fecha = models.DateField()
    
    # FK si es personal
    personal = models.ForeignKey(Usuario, on_delete=models.CASCADE, null=True, blank=True)
    
    # Datos si es estudiante
    estudiante_cedula = models.CharField(max_length=20, blank=True)
    estudiante_nombre = models.CharField(max_length=200, blank=True)
    
    asistio = models.BooleanField(default=False)
    
    # Auditoria
    registrado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, related_name='asistencias_registradas')
    fecha_registro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tipo} - {self.fecha} - Asistio: {self.asistio}"

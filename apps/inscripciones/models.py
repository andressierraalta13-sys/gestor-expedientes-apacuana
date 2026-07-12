from django.db import models
from estudiantes.models import Estudiante

class PeriodoAcademico(models.Model):
    nombre = models.CharField(max_length=50, unique=True, help_text="Ej: 2025-2026")
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} {'(Activo)' if self.activo else '(Cerrado)'}"

class Asignatura(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=150)
    ano_grado = models.IntegerField(help_text="Ej: 1, 2, 3, 4, 5 (Años de Bachillerato)")

    def __str__(self):
        return f"{self.codigo} - {self.nombre} ({self.ano_grado} Año)"

class Inscripcion(models.Model):
    estudiante = models.ForeignKey(Estudiante, on_delete=models.CASCADE, related_name='inscripciones')
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.PROTECT, related_name='inscripciones')
    ano_grado = models.IntegerField()
    seccion = models.CharField(max_length=5)
    
    class Meta:
        unique_together = ('estudiante', 'periodo')

    def __str__(self):
        return f"{self.estudiante.cedula_identidad} - {self.periodo.nombre} ({self.ano_grado} {self.seccion})"

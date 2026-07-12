from django.db import models
from estudiantes.models import Estudiante

class RegistroRiesgo(models.Model):
    """
    Motor Algorítmico: Almacena un historial de análisis de riesgo
    académico y documental para un estudiante en un punto en el tiempo.
    """
    estudiante = models.ForeignKey(Estudiante, on_delete=models.CASCADE, related_name='registros_riesgo')
    nivel_riesgo_global = models.FloatField(default=0.0, help_text="Puntuación de 0 a 100")
    materias_reprobadas = models.IntegerField(default=0)
    faltas_documentales = models.IntegerField(default=0)
    banderas_rojas = models.JSONField(default=list, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Registro de Riesgo"
        verbose_name_plural = "Registros de Riesgo"

    def __str__(self):
        return f"Riesgo {self.nivel_riesgo_global}% - {self.estudiante.cedula_identidad}"

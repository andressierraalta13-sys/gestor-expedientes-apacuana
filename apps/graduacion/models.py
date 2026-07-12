from django.db import models
from estudiantes.models import Estudiante

class TituloBachiller(models.Model):
    estudiante = models.OneToOneField(Estudiante, on_delete=models.CASCADE, related_name='titulo')
    fecha_emision = models.DateField()
    numero_registro = models.CharField(max_length=50, unique=True, help_text="Folio/Libro/Acta")
    codigo_qr_hash = models.CharField(max_length=255, unique=True)
    ruta_pdf = models.FileField(upload_to='titulos_generados/', blank=True, null=True)

    def __str__(self):
        return f"Título de {self.estudiante.nombres} {self.estudiante.apellidos} - {self.numero_registro}"

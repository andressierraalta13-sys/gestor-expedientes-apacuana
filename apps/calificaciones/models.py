from django.db import models
from inscripciones.models import Inscripcion, Asignatura
from simple_history.models import HistoricalRecords
from django.conf import settings
from django.core.files.storage import FileSystemStorage


class Calificacion(models.Model):
    TIPO_OPCIONES = (
        ('L1', 'Primer Lapso'),
        ('L2', 'Segundo Lapso'),
        ('L3', 'Tercer Lapso'),
        ('DEF', 'Definitiva'),
        ('REP', 'Reparación'),
    )
    inscripcion = models.ForeignKey(Inscripcion, on_delete=models.CASCADE, related_name='calificaciones')
    asignatura = models.ForeignKey(Asignatura, on_delete=models.PROTECT)
    nota = models.FloatField()
    tipo = models.CharField(max_length=15, choices=TIPO_OPCIONES, default='DEF')
    fecha_carga = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = "Calificaciones"

    def __str__(self):
        return f"{self.inscripcion.estudiante.cedula_identidad} - {self.asignatura.codigo}: {self.nota}"


def select_raw_storage():
    backend = settings.STORAGES.get("default", {}).get("BACKEND", "")
    if "CloudinaryStorage" in backend:
        from cloudinary_storage.storage import RawMediaCloudinaryStorage
        return RawMediaCloudinaryStorage()
    return FileSystemStorage()


class NotaCertificada(models.Model):
    """
    Registro de cada expediente de Notas Certificadas generado a partir de un
    archivo Excel subido por el usuario.  Guarda una copia individual del .xlsx
    con el formato intacto para descarga individual o unificación masiva.
    """
    cedula_normalizada = models.CharField(
        max_length=20,
        verbose_name="Cédula (normalizada)",
        help_text="Cédula sin puntos, comas ni espacios",
    )
    nombre_completo = models.CharField(max_length=250, verbose_name="Nombre completo")
    nombres         = models.CharField(max_length=150, blank=True, default="")
    apellidos       = models.CharField(max_length=150, blank=True, default="")
    archivo_pdf    = models.FileField(
        upload_to='notas_certificadas/',
        verbose_name="Archivo PDF generado",
    )
    nombre_archivo_original = models.CharField(max_length=255, blank=True, default="")
    fecha_carga     = models.DateTimeField(auto_now_add=True)
    cargado_por     = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        verbose_name        = "Nota Certificada"
        verbose_name_plural = "Notas Certificadas"
        ordering            = ['-fecha_carga']

    def __str__(self):
        return f"{self.cedula_normalizada} — {self.nombre_completo}"


from django.db import models
from django.utils.timezone import now
from simple_history.models import HistoricalRecords


class SoftDeleteManager(models.Manager):
    """Manager por defecto que excluye registros inactivados (soft delete)."""
    def get_queryset(self):
        return super().get_queryset().filter(activo=True)


class AllObjectsManager(models.Manager):
    """Manager alternativo que retorna TODOS los registros, incluyendo inactivos."""
    def get_queryset(self):
        return super().get_queryset()

class Estudiante(models.Model):
    cedula_identidad = models.CharField(max_length=15, unique=True)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField()
    sexo = models.CharField(max_length=15, blank=True, null=True)
    lugar_nacimiento = models.CharField(max_length=150, blank=True, null=True)
    pais_nacimiento = models.CharField(max_length=100, default="Venezuela", blank=True, null=True, verbose_name="País de Nacimiento")
    estado_nacimiento = models.CharField(max_length=100, blank=True, null=True, verbose_name="Estado de Nacimiento")
    municipio_nacimiento = models.CharField(max_length=100, blank=True, null=True, verbose_name="Municipio de Nacimiento")
    fecha_ingreso = models.DateField(auto_now_add=True, null=True)
    zona_educativa = models.CharField(max_length=150, default="U.E.N Colegio Apacuana")
    codigo_plantel = models.CharField(max_length=50, default="OD24061508")
    codigo_plan_estudio = models.CharField(max_length=10, blank=True, null=True)
    telefono_representante = models.CharField(max_length=20, blank=True, null=True, verbose_name="Teléfono del Representante")
    email_representante = models.EmailField(blank=True, null=True, verbose_name="Correo del Representante")
    nombre_representante = models.CharField(max_length=200, blank=True, null=True, verbose_name="Nombre del Representante")
    cedula_representante = models.CharField(max_length=20, blank=True, null=True, verbose_name="C.I. del Representante")
    
    ANO_CURSANDO_CHOICES = (
        (11, '1er Grado'),
        (12, '2do Grado'),
        (13, '3er Grado'),
        (14, '4to Grado'),
        (15, '5to Grado'),
        (16, '6to Grado'),
        (1, '1er Año'),
        (2, '2do Año'),
        (3, '3er Año'),
        (4, '4to Año'),
        (5, '5to Año'),
        (6, 'Egresado/Graduado'),
    )
    ano_cursando = models.IntegerField(choices=ANO_CURSANDO_CHOICES, default=1, verbose_name="Grado/Año que cursa")
    seccion = models.CharField(max_length=1, blank=True, null=True, verbose_name="Sección")

    # ── Fechas de Culminación de Años Académicos ─────────────────────────────
    mes_culminacion_1er_ano = models.CharField(max_length=2, blank=True, null=True, verbose_name="Mes Culminación 1er Año")
    ano_culminacion_1er_ano = models.CharField(max_length=4, blank=True, null=True, verbose_name="Año Culminación 1er Año")
    mes_culminacion_2do_ano = models.CharField(max_length=2, blank=True, null=True, verbose_name="Mes Culminación 2do Año")
    ano_culminacion_2do_ano = models.CharField(max_length=4, blank=True, null=True, verbose_name="Año Culminación 2do Año")
    mes_culminacion_3er_ano = models.CharField(max_length=2, blank=True, null=True, verbose_name="Mes Culminación 3er Año")
    ano_culminacion_3er_ano = models.CharField(max_length=4, blank=True, null=True, verbose_name="Año Culminación 3er Año")
    mes_culminacion_4to_ano = models.CharField(max_length=2, blank=True, null=True, verbose_name="Mes Culminación 4to Año")
    ano_culminacion_4to_ano = models.CharField(max_length=4, blank=True, null=True, verbose_name="Año Culminación 4to Año")
    mes_culminacion_5to_ano = models.CharField(max_length=2, blank=True, null=True, verbose_name="Mes Culminación 5to Año")
    ano_culminacion_5to_ano = models.CharField(max_length=4, blank=True, null=True, verbose_name="Año Culminación 5to Año")

    activo             = models.BooleanField(default=True, help_text='Obsoleto: el borrado de estudiantes es físico y definitivo.')
    fecha_inactivacion = models.DateTimeField(null=True, blank=True, help_text='Obsoleto.')

    # Managers: objects y objects_all retornan todos los estudiantes reales en BD
    objects     = models.Manager()
    objects_all = models.Manager()

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.cedula_identidad} - {self.nombres} {self.apellidos}"


class Expediente(models.Model):
    ESTATUS_OPCIONES = (
        ('SOLVENTE', 'Solvente'),
        ('INCOMPLETO', 'Incompleto'),
    )
    estudiante = models.OneToOneField(Estudiante, on_delete=models.CASCADE, related_name='expediente')
    numero_expediente = models.CharField(max_length=50, blank=True, null=True, verbose_name="Número de Expediente")
    copia_cedula = models.BooleanField(default=False)
    archivo_cedula = models.FileField(upload_to='archivos/cedulas/', blank=True, null=True)
    
    partida_nacimiento = models.BooleanField(default=False)
    archivo_partida = models.FileField(upload_to='archivos/partidas/', blank=True, null=True)
    
    notas_certificadas_previas = models.BooleanField(default=False)
    archivo_notas = models.FileField(upload_to='archivos/notas/', blank=True, null=True)
    
    fotografias = models.BooleanField(default=False)
    archivo_fotos = models.FileField(upload_to='archivos/fotos/', blank=True, null=True)
    estatus = models.CharField(max_length=15, choices=ESTATUS_OPCIONES, default='INCOMPLETO')
    observaciones = models.TextField(blank=True, null=True)
    
    history = HistoricalRecords()

    def verificar_solvencia(self):
        if self.copia_cedula and self.partida_nacimiento and self.notas_certificadas_previas and self.fotografias:
            self.estatus = 'SOLVENTE'
        else:
            self.estatus = 'INCOMPLETO'
        self.save()

    def __str__(self):
        return f"Expediente - {self.estudiante.cedula_identidad} ({self.get_estatus_display()})"

class ObservacionConductual(models.Model):
    estudiante = models.ForeignKey(Estudiante, on_delete=models.CASCADE, related_name='observaciones_conductuales')
    asunto = models.CharField(max_length=255)
    descripcion = models.TextField()
    fecha_registro = models.DateTimeField(auto_now_add=True)
    
    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = "Observaciones Conductuales"
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"{self.estudiante.cedula_identidad} - {self.asunto}"

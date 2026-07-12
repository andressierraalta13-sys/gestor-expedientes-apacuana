from django.db import models
from inscripciones.models import Asignatura, PeriodoAcademico
from usuarios.models import Usuario

class Aula(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    capacidad = models.IntegerField(default=30)
    ubicacion = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.nombre

class Horario(models.Model):
    ano_grado = models.IntegerField(help_text="Año del grado académico (1, 2, 3...)")
    seccion = models.CharField(max_length=5, help_text="Sección (A, B, C...)")
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.CASCADE, related_name="horarios")

    class Meta:
        unique_together = ('ano_grado', 'seccion', 'periodo')
        verbose_name = "Horario"
        verbose_name_plural = "Horarios"

    def __str__(self):
        return f"{self.ano_grado}-{self.seccion} ({self.periodo.nombre})"

class BloqueHorario(models.Model):
    TIPO_BLOQUE_CHOICES = (
        ('CLASE', 'Clase Académica'),
        ('RECESO', 'Receso'),
        ('ALMUERZO', 'Almuerzo'),
        ('OTRO', 'Otro Evento Especial')
    )
    DIA_CHOICES = (
        ('1', 'Lunes'),
        ('2', 'Martes'),
        ('3', 'Miércoles'),
        ('4', 'Jueves'),
        ('5', 'Viernes'),
        ('6', 'Sábado'),
        ('0', 'Domingo'),
    )

    horario = models.ForeignKey(Horario, on_delete=models.CASCADE, related_name="bloques")
    tipo = models.CharField(max_length=15, choices=TIPO_BLOQUE_CHOICES, default='CLASE')
    
    dia_semana = models.CharField(max_length=1, choices=DIA_CHOICES)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    asignatura = models.ForeignKey(Asignatura, on_delete=models.SET_NULL, null=True, blank=True)
    docente = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'rol': 'DOCENTE'})
    aula = models.ForeignKey(Aula, on_delete=models.SET_NULL, null=True, blank=True)

    # ── Campos de integración Nómina (texto libre) ──────────────────────────
    # docente_nombre proviene del modelo Personal (pagos), filtrado por nómina.
    # aula_numero almacena el número del aula como texto numérico validado.
    docente_nombre = models.CharField(max_length=255, blank=True, default='',
                                      help_text='Nombre del docente vinculado a la nómina.')
    aula_numero    = models.CharField(max_length=10,  blank=True, default='',
                                      help_text='Número de aula (solo dígitos).')

    color_hex = models.CharField(max_length=7, default="#6366F1", help_text="Color para visualizar en el calendario")

    class Meta:
        verbose_name = "Bloque de Horario"
        verbose_name_plural = "Bloques de Horario"

    def __str__(self):
        return f"{self.get_tipo_display()} {self.get_dia_semana_display()} {self.hora_inicio}-{self.hora_fin}"

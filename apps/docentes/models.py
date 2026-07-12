from django.db import models
from django.conf import settings
from django.db.models import Sum
from inscripciones.models import Asignatura, PeriodoAcademico, Inscripcion

ESTADOS_VENEZUELA = [
    ('AMAZONAS',      'Amazonas'),
    ('ANZOATEGUI',    'Anzoátegui'),
    ('APURE',         'Apure'),
    ('ARAGUA',        'Aragua'),
    ('BARINAS',       'Barinas'),
    ('BOLIVAR',       'Bolívar'),
    ('CARABOBO',      'Carabobo'),
    ('COJEDES',       'Cojedes'),
    ('DELTA_AMACURO', 'Delta Amacuro'),
    ('DTTO_CAPITAL',  'Distrito Capital'),
    ('FALCON',        'Falcón'),
    ('GUARICO',       'Guárico'),
    ('LARA',          'Lara'),
    ('MERIDA',        'Mérida'),
    ('MIRANDA',       'Miranda'),
    ('MONAGAS',       'Monagas'),
    ('NUEVA_ESPARTA', 'Nueva Esparta'),
    ('PORTUGUESA',    'Portuguesa'),
    ('SUCRE',         'Sucre'),
    ('TACHIRA',       'Táchira'),
    ('TRUJILLO',      'Trujillo'),
    ('LA_GUAIRA',     'La Guaira'),
    ('YARACUY',       'Yaracuy'),
    ('ZULIA',         'Zulia'),
]


class AsignacionDocente(models.Model):
    """Vincula un docente con una sección y asignatura en un período específico."""
    docente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='asignaciones',
        limit_choices_to={'rol': 'DOCENTE'}
    )
    asignatura = models.ForeignKey(Asignatura, on_delete=models.CASCADE, related_name='asignaciones')
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.CASCADE, related_name='asignaciones')
    ano_grado = models.IntegerField()
    seccion = models.CharField(max_length=5)
    aula = models.CharField(max_length=50, blank=True, null=True, verbose_name="Aula")
    activa = models.BooleanField(default=True)

    class Meta:
        unique_together = ('docente', 'asignatura', 'periodo', 'seccion')
        verbose_name = 'Asignación Docente'
        verbose_name_plural = 'Asignaciones Docentes'

    def __str__(self):
        return f"{self.docente.username} → {self.asignatura.nombre} ({self.ano_grado}{self.seccion}) [{self.periodo.nombre}]"


class Evaluacion(models.Model):
    TIPO_CHOICES = [
        ('EXAMEN', 'Examen'),
        ('TAREA', 'Tarea'),
        ('PARTICIPACION', 'Participación'),
        ('PROYECTO', 'Proyecto'),
        ('PRACTICO', 'Trabajo Práctico'),
        ('OTRO', 'Otro'),
    ]

    asignatura = models.ForeignKey(Asignatura, on_delete=models.CASCADE, related_name='evaluaciones')
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.CASCADE, related_name='evaluaciones')
    seccion = models.CharField(max_length=5, default='U')
    nombre = models.CharField(max_length=200)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='EXAMEN')
    ponderacion = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Porcentaje de la nota final (1-100)"
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='evaluaciones_creadas'
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Evaluación'
        verbose_name_plural = 'Evaluaciones'
        ordering = ['fecha_creacion']

    def __str__(self):
        return f"{self.nombre} ({self.ponderacion}%) – {self.asignatura.nombre}"

    @classmethod
    def suma_ponderacion(cls, asignatura_id, periodo_id, seccion):
        resultado = cls.objects.filter(
            asignatura_id=asignatura_id,
            periodo_id=periodo_id,
            seccion=seccion,
            activa=True
        ).aggregate(total=Sum('ponderacion'))
        return float(resultado['total'] or 0)


class NotaEvaluacion(models.Model):
    """Nota de un estudiante en una evaluación específica."""
    inscripcion = models.ForeignKey(
        Inscripcion, on_delete=models.CASCADE, related_name='notas_evaluaciones'
    )
    evaluacion = models.ForeignKey(
        Evaluacion, on_delete=models.CASCADE, related_name='notas'
    )
    nota = models.FloatField(help_text="Nota en escala 0–20")
    asistencia = models.BooleanField(default=True, verbose_name="Asistencia")
    observacion = models.TextField(max_length=1000, blank=True, null=True, verbose_name="Observación")
    es_borrador = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(auto_now=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='notas_registradas'
    )

    class Meta:
        unique_together = ('inscripcion', 'evaluacion')
        verbose_name = 'Nota de Evaluación'
        verbose_name_plural = 'Notas de Evaluaciones'

    def __str__(self):
        return f"{self.inscripcion.estudiante} – {self.evaluacion.nombre}: {self.nota}"


class PeriodoCierre(models.Model):
    """Bloquea modificaciones en notas para una asignatura/sección en un período."""
    asignatura = models.ForeignKey(Asignatura, on_delete=models.CASCADE, related_name='cierres')
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.CASCADE, related_name='cierres')
    seccion = models.CharField(max_length=5, default='U')
    cerrado = models.BooleanField(default=False)
    cerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='cierres_realizados'
    )
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('asignatura', 'periodo', 'seccion')
        verbose_name = 'Cierre de Período'
        verbose_name_plural = 'Cierres de Período'

    def __str__(self):
        estado = "Cerrado" if self.cerrado else "Abierto"
        return f"{self.asignatura.nombre} – {self.periodo.nombre} ({self.seccion}) [{estado}]"


class PerfilDocente(models.Model):
    """Datos personales y de contacto del docente, gestionado desde el panel administrativo."""
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='perfil_docente'
    )
    cedula = models.CharField(max_length=20, unique=True, blank=True, null=True, verbose_name="Cédula")
    nombre = models.CharField(max_length=100, blank=True, default='')
    apellidos = models.CharField(max_length=100, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    telefono = models.CharField(max_length=20, blank=True, default='')
    estado_residencia = models.CharField(
        max_length=20, choices=ESTADOS_VENEZUELA, blank=True, default=''
    )
    foto_perfil = models.ImageField(upload_to='docentes/perfiles/', blank=True, null=True, verbose_name="Foto de Perfil")
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Perfil Docente'
        verbose_name_plural = 'Perfiles Docentes'

    def __str__(self):
        return f"Perfil: {self.usuario.username}"

    @property
    def nombre_completo(self):
        if self.nombre and self.apellidos:
            return f"{self.nombre} {self.apellidos}"
        return self.usuario.nombre_completo or self.usuario.username


class TemaClase(models.Model):
    """Representa una semana o tema del cronograma de clases."""
    asignatura = models.ForeignKey(Asignatura, on_delete=models.CASCADE, related_name='temas_clase')
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.CASCADE, related_name='temas_clase')
    seccion = models.CharField(max_length=5, default='U')
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    fecha_programada = models.DateField(null=True, blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True,
        related_name='temas_creados'
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'Tema de Clase'
        verbose_name_plural = 'Temas de Clase'
        ordering = ['fecha_programada', 'fecha_creacion']

    def __str__(self):
        return f"{self.titulo} - {self.asignatura.nombre} ({self.seccion})"


class MaterialApoyo(models.Model):
    """Archivos o enlaces de apoyo para un tema de clase."""
    tema = models.ForeignKey(TemaClase, on_delete=models.CASCADE, related_name='materiales')
    titulo = models.CharField(max_length=200)
    archivo = models.FileField(upload_to='docentes/materiales/', blank=True, null=True)
    enlace = models.URLField(max_length=500, blank=True, null=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
        related_name='+'
    )

    class Meta:
        verbose_name = 'Material de Apoyo'
        verbose_name_plural = 'Materiales de Apoyo'
        
    def __str__(self):
        return f"{self.titulo} - {self.tema.titulo}"


class TareaDocente(models.Model):
    """Tareas asignadas a los estudiantes para un tema específico."""
    tema = models.ForeignKey(TemaClase, on_delete=models.CASCADE, related_name='tareas')
    titulo = models.CharField(max_length=200)
    instrucciones = models.TextField()
    fecha_entrega = models.DateTimeField(null=True, blank=True)
    evaluacion_vinculada = models.OneToOneField(
        'Evaluacion', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='tarea_origen',
        help_text="Opcional: Si esta tarea tiene calificación, se vincula a una Evaluación."
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    activa = models.BooleanField(default=True)
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
        related_name='tareas_creadas'
    )

    class Meta:
        verbose_name = 'Tarea Asignada'
        verbose_name_plural = 'Tareas Asignadas'
        ordering = ['fecha_entrega']

    def __str__(self):
        return f"Tarea: {self.titulo} ({self.tema.titulo})"


class RegistroAsistencia(models.Model):
    """Registro de asistencia de un estudiante en una materia/sección/día."""
    ESTADO_CHOICES = [
        ('PRESENTE', 'Presente'),
        ('AUSENTE', 'Ausente'),
        ('RETARDO', 'Retardo'),
        ('JUSTIFICADO', 'Justificado'),
    ]
    METODO_CHOICES = [
        ('MANUAL', 'Manual'),
        ('QR', 'Código QR'),
        ('GPS', 'Geolocalización'),
    ]

    estudiante = models.ForeignKey(
        'estudiantes.Estudiante',
        on_delete=models.CASCADE,
        related_name='asistencias_docente'
    )
    asignatura = models.ForeignKey(Asignatura, on_delete=models.CASCADE, related_name='asistencias_docente')
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.CASCADE, related_name='asistencias_docente')
    seccion = models.CharField(max_length=5, default='U')
    fecha = models.DateField(verbose_name='Fecha de la clase')
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='PRESENTE')
    observacion = models.TextField(max_length=500, blank=True, default='')
    metodo = models.CharField(max_length=10, choices=METODO_CHOICES, default='MANUAL')
    hora_registro = models.DateTimeField(auto_now_add=True)
    hora_llegada = models.TimeField(null=True, blank=True, verbose_name='Hora de llegada')
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
        related_name='asistencias_docente_registradas'
    )

    class Meta:
        unique_together = ('estudiante', 'asignatura', 'periodo', 'seccion', 'fecha')
        verbose_name = 'Registro de Asistencia'
        verbose_name_plural = 'Registros de Asistencia'
        ordering = ['-fecha', 'estudiante']

    def __str__(self):
        return f"{self.estudiante} – {self.fecha} – {self.estado}"

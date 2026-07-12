from django.db import models
from django.conf import settings
from django.utils.timezone import now
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# AUDITORÍA TÉCNICA DEL DESARROLLADOR
# ═══════════════════════════════════════════════════════════════════════════════

class DevAuditoriaLog(models.Model):
    """
    Registro técnico detallado de acciones realizadas por el Desarrollador.
    Captura trazabilidad completa: IP, SQL exacto, tiempo de ejecución, filas.
    """

    ACCION_CHOICES = [
        ('SQL_EXECUTE',    'Ejecución SQL'),
        ('SQL_MODIFY',     'Modificación SQL'),
        ('EXPORT_DB',      'Exportación de BD'),
        ('RESTORE_DB',     'Restauración de BD'),
        ('CLEAR_CACHE',    'Limpieza de Caché'),
        ('PURGE_AUDIT',    'Purga de Auditoría'),
        ('TEST_ERROR',     'Test de Excepción'),
        ('LOGIN',          'Inicio de Sesión'),
        ('LOGOUT',         'Cierre de Sesión'),
        ('VIEW_PANEL',     'Acceso al Panel'),
        ('EXPORT_LOGS',    'Exportación de Logs'),
        ('EXPORT_AUDIT',   'Exportación de Auditoría'),
        ('OTHER',          'Otra Acción'),
    ]

    RIESGO_CHOICES = [
        ('CRITICO',     '🔴 Crítico'),
        ('ADVERTENCIA', '🟠 Advertencia'),
        ('INFORMATIVO', '🔵 Informativo'),
    ]

    accion         = models.CharField(max_length=30, choices=ACCION_CHOICES, default='OTHER')
    usuario        = models.CharField(max_length=150, default='Desconocido')
    ip_address     = models.GenericIPAddressField(null=True, blank=True)
    timestamp      = models.DateTimeField(auto_now_add=True, db_index=True)
    nivel_riesgo   = models.CharField(max_length=15, choices=RIESGO_CHOICES, default='INFORMATIVO')
    # SQL específico
    query_sql      = models.TextField(blank=True, default='')
    rows_affected  = models.IntegerField(null=True, blank=True)
    execution_ms   = models.FloatField(null=True, blank=True)
    # Detalle genérico
    descripcion    = models.TextField(blank=True, default='')
    payload_json   = models.JSONField(null=True, blank=True)
    exitoso        = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Log Técnico Desarrollador'
        verbose_name_plural = 'Logs Técnicos Desarrollador'
        ordering            = ['-timestamp']
        indexes             = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['accion', '-timestamp']),
            models.Index(fields=['nivel_riesgo']),
        ]

    def __str__(self):
        return f"[{self.accion}] {self.usuario} @ {self.ip_address} — {self.timestamp:%d/%m/%Y %I:%M:%S %p}"


def registrar_dev_audit(
    accion: str,
    usuario: str = 'Sistema',
    ip_address: str = None,
    descripcion: str = '',
    query_sql: str = '',
    rows_affected: int = None,
    execution_ms: float = None,
    nivel_riesgo: str = 'INFORMATIVO',
    payload_json=None,
    exitoso: bool = True,
) -> 'DevAuditoriaLog | None':
    """Registra una acción técnica del desarrollador con trazabilidad completa."""
    try:
        return DevAuditoriaLog.objects.create(
            accion=accion,
            usuario=usuario,
            ip_address=ip_address,
            descripcion=descripcion,
            query_sql=query_sql,
            rows_affected=rows_affected,
            execution_ms=execution_ms,
            nivel_riesgo=nivel_riesgo,
            payload_json=payload_json,
            exitoso=exitoso,
        )
    except Exception as e:
        logger.error(f"[DevAuditoria] No se pudo registrar acción '{accion}': {e}", exc_info=True)
        return None


class EventoAuditoria(models.Model):
    """
    Registro centralizado y semántico de eventos de auditoría del sistema.
    Cada registro captura QUÉ cambió, QUIÉN lo hizo, CUÁNDO, y cuál fue el impacto.
    """

    TIPO_CHOICES = [
        # Pagos
        ('PAGO_MASIVO_OK',    'Pago Masivo Exitoso'),
        ('PAGO_MASIVO_ERROR', 'Pago Masivo con Error'),
        ('PAGO_INDIVIDUAL',  'Pago Individual'),
        # CRUD
        ('CREACION',         'Creación de Registro'),
        ('MODIFICACION',     'Modificación de Datos'),
        ('INACTIVACION',     'Inactivación de Registro'),
        # Seguridad
        ('BLOQUEO_DELETE',   'Intento de Eliminación Bloqueado'),
        ('LOGIN',            'Inicio de Sesión'),
        ('ACCESO_DENEGADO',  'Acceso Denegado'),
        # Sistema de Aprobaciones
        ('SOLICITUD_CONTROLADA', 'Acción Controlada por Solicitud'),
        ('SOLICITUD_APROBADA',   'Solicitud Aprobada por Administrativo'),
        ('SOLICITUD_RECHAZADA',  'Solicitud Rechazada por Administrativo'),
        # IA
        ('IA_CONSULTA',      'Consulta al Asistente IA'),
        ('IA_INCONSISTENCIA','IA Detectó Inconsistencia'),
        # Otros
        ('OTRO',             'Otro Evento'),
    ]

    RIESGO_CHOICES = [
        ('CRITICO',      '🔴 Crítico'),
        ('MEDIO',        '🟡 Medio'),
        ('INFORMATIVO',  '🔵 Informativo'),
    ]

    tipo          = models.CharField(max_length=30, choices=TIPO_CHOICES, default='OTRO')
    nivel_riesgo  = models.CharField(max_length=15, choices=RIESGO_CHOICES, default='INFORMATIVO')
    descripcion   = models.TextField()
    modulo        = models.CharField(max_length=100, blank=True, default='')
    usuario       = models.CharField(max_length=150, blank=True, default='Sistema')
    impacto       = models.CharField(max_length=255, blank=True, default='',
                                     help_text='Descripción del efecto del cambio en el sistema.')
    valor_anterior = models.JSONField(null=True, blank=True,
                                      help_text='Estado del registro ANTES del cambio.')
    valor_nuevo    = models.JSONField(null=True, blank=True,
                                      help_text='Estado del registro DESPUÉS del cambio.')
    detalle_json   = models.JSONField(null=True, blank=True,
                                      help_text='Datos adicionales estructurados del evento.')
    timestamp      = models.DateTimeField(auto_now_add=True)
    exitoso        = models.BooleanField(default=True)
    leido          = models.BooleanField(default=False,
                                         help_text='Indica si la notificación fue vista en el dashboard.')

    class Meta:
        verbose_name        = 'Evento de Auditoría'
        verbose_name_plural = 'Eventos de Auditoría'
        ordering            = ['-timestamp']
        indexes             = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['nivel_riesgo', 'leido']),
            models.Index(fields=['tipo']),
        ]

    def __str__(self):
        return f"[{self.get_nivel_riesgo_display()}][{self.get_tipo_display()}] {self.usuario} — {self.timestamp:%d/%m/%Y %I:%M %p}"


# ─── Función utilitaria reutilizable ──────────────────────────────────────────

def registrar_evento(
    tipo: str,
    descripcion: str,
    modulo: str = '',
    usuario: str = 'Sistema',
    nivel_riesgo: str = 'INFORMATIVO',
    exitoso: bool = True,
    impacto: str = '',
    valor_anterior=None,
    valor_nuevo=None,
    detalle_json=None,
) -> 'EventoAuditoria | None':
    """
    Función de conveniencia para registrar un evento de auditoría desde cualquier módulo.
    Ejemplo de uso:
        from auditoria.models import registrar_evento
        registrar_evento(
            tipo='MODIFICACION',
            descripcion='Calificación actualizada para estudiante V-12345678',
            modulo='Calificaciones',
            usuario=str(request.user),
            nivel_riesgo='MEDIO',
            valor_anterior={'nota': 15}, valor_nuevo={'nota': 18},
            impacto='Nota subió 3 puntos — puede afectar promedio definitivo.',
        )
    """
    try:
        evento = EventoAuditoria.objects.create(
            tipo=tipo,
            descripcion=descripcion,
            modulo=modulo,
            usuario=usuario,
            nivel_riesgo=nivel_riesgo,
            exitoso=exitoso,
            impacto=impacto,
            valor_anterior=valor_anterior,
            valor_nuevo=valor_nuevo,
            detalle_json=detalle_json,
        )
        return evento
    except Exception as e:
        logger.error(f"[Auditoría] No se pudo registrar evento '{tipo}': {e}", exc_info=True)
        return None

# ─── SISTEMA INTELIGENTE DE NOTIFICACIONES OPERATIVAS ────────────────────────

class NotificacionOperativa(models.Model):
    """
    Alertas operativas diseñadas para la campana de notificaciones.
    Se separa del log técnico de auditoría para mostrar solo eventos útiles (pagos, riesgos).
    """
    RIESGO_CHOICES = [
        ('CRITICO',      '🔴 Crítico'),
        ('ADVERTENCIA',  '🟡 Advertencia'),
        ('INFORMATIVO',  '🔵 Informativo'),
    ]

    titulo = models.CharField(max_length=200)
    mensaje = models.TextField()
    nivel_riesgo = models.CharField(max_length=15, choices=RIESGO_CHOICES, default='INFORMATIVO')
    modulo = models.CharField(max_length=100, blank=True, default='')
    leido = models.BooleanField(default=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    agrupacion_hash = models.CharField(max_length=255, blank=True, default='', db_index=True,
                                       help_text='Identificador para agrupar alertas similares no leídas.')
    conteo_agrupacion = models.IntegerField(default=1, 
                                            help_text='Cantidad de veces que ocurrió este evento agrupado.')

    class Meta:
        verbose_name = 'Notificación Operativa'
        verbose_name_plural = 'Notificaciones Operativas'
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"[{self.nivel_riesgo}] {self.titulo} (x{self.conteo_agrupacion})"


def lanzar_alerta_operativa(
    titulo: str,
    mensaje: str,
    nivel_riesgo: str = 'INFORMATIVO',
    modulo: str = '',
    agrupacion_hash: str = ''
) -> 'NotificacionOperativa | None':
    """
    Función para emitir una alerta a la campana del dashboard.
    Si se provee agrupacion_hash y ya existe una notificación no leída con ese hash, 
    incrementa el conteo en lugar de crear una nueva.
    """
    try:
        if agrupacion_hash:
            # Buscar si hay una alerta no leída con este hash
            alerta = NotificacionOperativa.objects.filter(
                agrupacion_hash=agrupacion_hash, 
                leido=False
            ).first()
            
            if alerta:
                # Incrementar conteo y actualizar mensaje/timestamp
                alerta.conteo_agrupacion += 1
                alerta.mensaje = mensaje  # Actualiza al mensaje más reciente
                alerta.fecha_creacion = now()
                alerta.save(update_fields=['conteo_agrupacion', 'mensaje', 'fecha_creacion'])
                return alerta

        # Si no existe o no tiene hash, crear nueva
        return NotificacionOperativa.objects.create(
            titulo=titulo,
            mensaje=mensaje,
            nivel_riesgo=nivel_riesgo,
            modulo=modulo,
            agrupacion_hash=agrupacion_hash
        )
    except Exception as e:
        logger.error(f"[Notificaciones] No se pudo lanzar alerta '{titulo}': {e}", exc_info=True)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# SISTEMA DE SOLICITUDES DE APROBACIÓN — Personal → Administrativo
# ═══════════════════════════════════════════════════════════════════════════════

class SolicitudAprobacion(models.Model):
    """
    Registro de una acción crítica que el usuario Personal quiso ejecutar
    pero requiere aprobación previa del Administrativo.
    Expira automáticamente a las 48 horas de su creación.
    """

    ESTADO_CHOICES = [
        ('PENDIENTE',  '🟡 Pendiente'),
        ('APROBADA',   '✅ Aprobada'),
        ('RECHAZADA',  '❌ Rechazada'),
        ('EXPIRADA',   '⏰ Expirada'),
    ]

    ACCION_CHOICES = [
        ('eliminar_evaluaciones',   'Eliminar Evaluaciones'),
        ('restablecer_materias',    'Restablecer Materias de Docente'),
        ('eliminar_horarios',       'Eliminar Horarios'),
        ('eliminar_expedientes',    'Eliminar Expedientes'),
        ('otra_accion',             'Otra Acción'),
    ]

    # ── Quién solicita ────────────────────────────────────────────────────────
    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='solicitudes_enviadas',
        verbose_name='Usuario solicitante'
    )

    # ── Qué acción quiere ejecutar ────────────────────────────────────────────
    accion = models.CharField(max_length=50, choices=ACCION_CHOICES, default='otra_accion')
    modulo = models.CharField(max_length=100, help_text='Módulo donde se quería actuar.')
    descripcion = models.TextField(
        help_text='Descripción clara de qué quería hacer el Personal y sobre qué objeto.'
    )
    payload_json = models.JSONField(
        null=True, blank=True,
        help_text='Datos de la acción (IDs a eliminar, etc.) para ejecutar al aprobar.'
    )

    # ── Estado y tiempos ──────────────────────────────────────────────────
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='PENDIENTE', db_index=True)
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_expiracion = models.DateTimeField(
        help_text='Fecha/hora a la que la solicitud expira automáticamente (48h desde creación).'
    )
    fecha_respuesta = models.DateTimeField(null=True, blank=True)

    # ── Respuesta del Administrativo ────────────────────────────────────────────
    procesado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='solicitudes_procesadas',
        verbose_name='Administrativo que respondió'
    )
    comentario_admin = models.TextField(
        blank=True, default='',
        max_length=1000,
        help_text='Comentario opcional del Administrativo al aprobar o rechazar.'
    )

    # ── Control de lectura para Personal ───────────────────────────────────
    leida_por_personal = models.BooleanField(
        default=False,
        help_text='Indica si el Personal ya vio la respuesta del Administrativo.'
    )

    class Meta:
        verbose_name = 'Solicitud de Aprobación'
        verbose_name_plural = 'Solicitudes de Aprobación'
        ordering = ['-fecha_solicitud']
        indexes = [
            models.Index(fields=['estado', '-fecha_solicitud']),
            models.Index(fields=['solicitante', 'leida_por_personal']),
        ]

    def __str__(self):
        return f"[{self.get_estado_display()}] {self.solicitante.username} → {self.get_accion_display()} ({self.fecha_solicitud:%d/%m/%Y %I:%M %p})"

    def save(self, *args, **kwargs):
        """Auto-calcular fecha de expiración a 48h si es nueva."""
        from datetime import timedelta
        if not self.pk:
            self.fecha_expiracion = now() + timedelta(hours=48)
        super().save(*args, **kwargs)

    @property
    def esta_expirada(self):
        return self.estado == 'PENDIENTE' and now() > self.fecha_expiracion

    @property
    def tiempo_restante_display(self):
        """Devuelve texto legible del tiempo restante para expirar."""
        if self.estado != 'PENDIENTE':
            return None
        delta = self.fecha_expiracion - now()
        if delta.total_seconds() <= 0:
            return 'Expirada'
        horas = int(delta.total_seconds() // 3600)
        minutos = int((delta.total_seconds() % 3600) // 60)
        if horas > 0:
            return f'{horas}h {minutos}min restantes'
        return f'{minutos}min restantes'


# ═══════════════════════════════════════════════════════════════════════════════
# CENTRO DE NOTIFICACIONES
# ═══════════════════════════════════════════════════════════════════════════════

class Notificacion(models.Model):
    TIPO_CHOICES = [
        ('AUDITORIA', 'Movimiento de Auditoría'),
        ('ACTUALIZACION', 'Nota de Actualización / Dev'),
        ('SISTEMA', 'Aviso General del Sistema'),
    ]
    
    titulo = models.CharField(max_length=150)
    mensaje = models.TextField()
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='AUDITORIA')
    creado_en = models.DateTimeField(auto_now_add=True)
    # Si es global (para todos), el usuario destino puede ser null
    usuario_destino = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='notificaciones')
    leido = models.BooleanField(default=False)

    class Meta:
        ordering = ['-creado_en']
        verbose_name = 'Notificación'
        verbose_name_plural = 'Notificaciones'

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.titulo}"

"""
Ejecutor de Solicitudes de Aprobación
======================================
Este módulo contiene el dispatcher que ejecuta la acción real
cuando un Administrativo aprueba una solicitud enviada por Personal.
"""
import logging
from django.utils.timezone import now

logger = logging.getLogger(__name__)


def ejecutar_accion_aprobada(solicitud) -> dict:
    """
    Dispatcher central. Ejecuta la acción definida en solicitud.accion
    usando los datos del payload_json.

    Retorna: {'ok': bool, 'mensaje': str}
    """
    accion = solicitud.accion
    payload = solicitud.payload_json or {}

    try:
        if accion == 'eliminar_evaluaciones':
            return _eliminar_evaluaciones(payload)

        elif accion == 'restablecer_materias':
            return _restablecer_materias(payload)

        elif accion == 'eliminar_horarios':
            return _eliminar_horarios(payload)

        elif accion == 'eliminar_expedientes':
            return _eliminar_expedientes(payload)

        elif accion == 'eliminar_observacion':
            return _eliminar_observacion(payload)

        else:
            return {'ok': False, 'mensaje': f'Acción desconocida: {accion}'}

    except Exception as e:
        logger.error(f"[Ejecutor] Error al ejecutar acción '{accion}': {e}", exc_info=True)
        return {'ok': False, 'mensaje': f'Error al ejecutar: {str(e)}'}


# ── Implementaciones de cada acción ──────────────────────────────────────────

def _eliminar_evaluaciones(payload: dict) -> dict:
    """Elimina físicamente evaluaciones y sus notas asociadas."""
    from docentes.models import Evaluacion, NotaEvaluacion
    ids = payload.get('evaluaciones_ids', [])
    if not ids:
        return {'ok': False, 'mensaje': 'No se proporcionaron IDs de evaluaciones.'}

    NotaEvaluacion.objects.filter(evaluacion_id__in=ids).delete()
    eliminados, _ = Evaluacion.objects.filter(id__in=ids).delete()
    return {'ok': True, 'mensaje': f'{eliminados} evaluación(es) eliminadas correctamente.'}


def _restablecer_materias(payload: dict) -> dict:
    """Desactiva (borrado lógico) todas las asignaciones activas de un docente."""
    from docentes.models import AsignacionDocente
    docente_id = payload.get('docente_id')
    if not docente_id:
        return {'ok': False, 'mensaje': 'No se proporcionó el ID del docente.'}

    count = AsignacionDocente.objects.filter(docente_id=docente_id, activa=True).update(activa=False)
    return {'ok': True, 'mensaje': f'{count} materia(s) restablecida(s) para el docente.'}


def _eliminar_horarios(payload: dict) -> dict:
    """Elimina físicamente horarios seleccionados."""
    from horarios.models import Horario
    ids = payload.get('horarios_ids', [])
    if not ids:
        return {'ok': False, 'mensaje': 'No se proporcionaron IDs de horarios.'}

    eliminados, _ = Horario.objects.filter(id__in=ids).delete()
    return {'ok': True, 'mensaje': f'{eliminados} horario(s) eliminado(s) correctamente.'}


def _eliminar_expedientes(payload: dict) -> dict:
    """Elimina físicamente expedientes de estudiantes seleccionados."""
    from estudiantes.models import Estudiante
    ids = payload.get('expedientes_ids', [])
    if not ids:
        return {'ok': False, 'mensaje': 'No se proporcionaron IDs de expedientes.'}

    eliminados, _ = Estudiante.objects_all.filter(expediente__id__in=ids).delete()
    return {'ok': True, 'mensaje': f'{eliminados} expediente(s) eliminado(s) correctamente.'}


def _eliminar_observacion(payload: dict) -> dict:
    """Elimina físicamente una observación conductual."""
    from estudiantes.models import ObservacionConductual
    obs_id = payload.get('observacion_id')
    if not obs_id:
        return {'ok': False, 'mensaje': 'No se proporcionó el ID de la observación.'}

    eliminados, _ = ObservacionConductual.objects.filter(id=obs_id).delete()
    return {'ok': True, 'mensaje': 'Registro conductual eliminado correctamente.'}

import logging
from estudiantes.models import Estudiante, ObservacionConductual
from calificaciones.models import Calificacion
from asistencias.models import RegistroAsistencia
from django.db.models import Avg

logger = logging.getLogger(__name__)


def evaluar_estudiante(emp):
    faltas_doc = 0
    es_solvente = False
    banderas = []
    
    # 1. 25% Documental
    try:
        exp = emp.expediente
        faltas = 0
        if not exp.copia_cedula: faltas += 1; banderas.append('Falta Cédula')
        if not exp.partida_nacimiento: faltas += 1; banderas.append('Falta Partida Nac.')
        if not exp.notas_certificadas_previas: faltas += 1; banderas.append('Faltan Notas Previas')
        if not exp.fotografias: faltas += 1
        faltas_doc = faltas
        if exp.estatus == 'SOLVENTE':
            es_solvente = True
    except Exception:
        faltas_doc = 4  # Peor caso si no tiene expediente creado
        banderas.append('Expediente Inexistente')
        
    peso_documental = (faltas_doc / 4.0) * 25.0
    
    # 2. 50% Académico
    notas_reprobadas = Calificacion.objects.filter(inscripcion__estudiante=emp, nota__lt=10.0).count()
    if notas_reprobadas > 0:
        banderas.append(f'{notas_reprobadas} Materia(s) Reprobada(s)')
    if notas_reprobadas >= 3:
        banderas.append('RIESGO CRÍTICO DE REPITENCIA')
        
    peso_academico = min((notas_reprobadas / 3.0) * 50.0, 50.0)
    
    # 3. 15% Conductual
    observaciones = ObservacionConductual.objects.filter(estudiante=emp).count()
    if observaciones >= 3:
        banderas.append(f'{observaciones} Faltas Conductuales Severas')
    elif observaciones > 0:
        banderas.append(f'{observaciones} Reportes de Conducta')
        
    peso_conductual = min((observaciones / 3.0) * 15.0, 15.0)
    
    # 4. 10% Asistencia
    inasistencias = RegistroAsistencia.objects.filter(estudiante_cedula=emp.cedula_identidad, asistio=False).count()
    total_asistencias = RegistroAsistencia.objects.filter(estudiante_cedula=emp.cedula_identidad).count()
    
    peso_asistencia = 0.0
    if total_asistencias > 0:
        tasa_inasistencia = inasistencias / float(total_asistencias)
        if tasa_inasistencia >= 0.20:
            banderas.append('ALTA INASISTENCIA (>20%)')
        peso_asistencia = min((tasa_inasistencia / 0.20) * 10.0, 10.0)
        
    riesgo_total = round(peso_documental + peso_academico + peso_conductual + peso_asistencia, 2)
    
    datos = {
        'nombres': emp.nombres,
        'apellidos': emp.apellidos,
        'cedula': emp.cedula_identidad,
        'materias_reprobadas': notas_reprobadas,
        'faltas_documentales': faltas_doc,
        'observaciones': observaciones,
        'inasistencias': inasistencias,
        'banderas': banderas,
        'es_solvente': es_solvente
    }
    
    return riesgo_total, datos


def actualizar_registro_inteligente(emp, riesgo_nuevo, datos):
    """Persiste el historial de riesgo solo si hay un cambio significativo.
    Si la tabla no existe (primer deploy sin migrate), lo ignora sin romper la vista."""
    try:
        from ia_analitica.models import RegistroRiesgo
        ultimo_registro = RegistroRiesgo.objects.filter(estudiante=emp).order_by('-timestamp').first()
        
        crear_nuevo = False
        
        if not ultimo_registro:
            crear_nuevo = True
        else:
            # Verificar diferencia significativa (> 5% de cambio en riesgo global)
            if abs(ultimo_registro.nivel_riesgo_global - riesgo_nuevo) > 5.0:
                crear_nuevo = True
            # O si las banderas cambiaron
            elif set(ultimo_registro.banderas_rojas) != set(datos['banderas']):
                crear_nuevo = True
                
        if crear_nuevo:
            RegistroRiesgo.objects.create(
                estudiante=emp,
                nivel_riesgo_global=riesgo_nuevo,
                materias_reprobadas=datos['materias_reprobadas'],
                faltas_documentales=datos['faltas_documentales'],
                banderas_rojas=datos['banderas']
            )
    except Exception as e:
        # Si la tabla no existe o hay un error de BD, lo registramos pero
        # NO detenemos el cálculo para no causar un 500 en la página de riesgos.
        logger.warning(f"[motor.py] No se pudo guardar RegistroRiesgo para {emp.cedula_identidad}: {e}")


def calcular_riesgos_globales():
    """Calcula riesgos para todos los estudiantes activos y devuelve métricas consolidadas."""
    try:
        estudiantes = Estudiante.objects.all()
    except Exception as e:
        logger.error(f"[motor.py] Error al obtener estudiantes: {e}")
        return [], {'promedio_global': 0.0, 'porcentaje_solventes': 0, 'tasa_reprobacion': 0}

    analisis_riesgos = []

    # Métricas Globales
    try:
        reprobados_totales = Calificacion.objects.filter(nota__lt=10.0).count()
        total_calificaciones = Calificacion.objects.count()
        tasa_reprobacion = int((reprobados_totales / total_calificaciones * 100)) if total_calificaciones > 0 else 0

        promedio_global = Calificacion.objects.filter(tipo='DEF').aggregate(Avg('nota'))['nota__avg']
        promedio_global = round(promedio_global, 2) if promedio_global else 0.0
    except Exception as e:
        logger.warning(f"[motor.py] Error en métricas globales de calificaciones: {e}")
        tasa_reprobacion = 0
        promedio_global = 0.0

    total_exp = estudiantes.count()
    solventes_count = 0

    for emp in estudiantes:
        try:
            riesgo, datos = evaluar_estudiante(emp)
            if datos['es_solvente']:
                solventes_count += 1

            actualizar_registro_inteligente(emp, riesgo, datos)

            if riesgo > 30:  # Mostrar en panel de riesgo crítico
                datos['riesgo'] = riesgo
                analisis_riesgos.append(datos)
        except Exception as e:
            logger.warning(f"[motor.py] Error evaluando estudiante {getattr(emp, 'cedula_identidad', '?')}: {e}")
            continue

    analisis_riesgos.sort(key=lambda x: x['riesgo'], reverse=True)

    pc_solventes = int((solventes_count / total_exp) * 100) if total_exp > 0 else 0

    metrics = {
        'promedio_global': promedio_global,
        'porcentaje_solventes': pc_solventes,
        'tasa_reprobacion': tasa_reprobacion
    }

    return analisis_riesgos, metrics

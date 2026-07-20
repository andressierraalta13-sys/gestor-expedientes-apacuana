import json
import requests
import traceback
from functools import wraps
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.db.models import Sum, Q
from django.utils.timezone import now

from inscripciones.models import Asignatura, PeriodoAcademico, Inscripcion
from estudiantes.models import Estudiante
import json
from functools import wraps
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.db.models import Sum, Q
from django.utils.timezone import now

from inscripciones.models import Asignatura, PeriodoAcademico, Inscripcion
from estudiantes.models import Estudiante
from auditoria.models import lanzar_alerta_operativa
from .models import AsignacionDocente, Evaluacion, NotaEvaluacion, PeriodoCierre, TemaClase, MaterialApoyo, TareaDocente


# ─── Decorador de Rol Docente ─────────────────────────────────────────────────

def docente_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.rol not in ['DOCENTE', 'DESARROLLADOR', 'PERSONAL', 'ADMINISTRATIVO', 'COORDINADOR']:
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return _wrapped


# ─── Vistas Principales del Portal ───────────────────────────────────────────

@docente_required
def dashboard_docente_view(request):
    docente = request.user
    asignaciones = list(AsignacionDocente.objects.filter(docente=docente, activa=True).select_related('asignatura', 'periodo'))
    for asig in asignaciones:
        asig.cantidad_alumnos = Estudiante.objects.filter(ano_cursando=asig.ano_grado, seccion=asig.seccion, activo=True).count()
    return render(request, 'docentes/dashboard_docente.html', {
        'docente': docente,
        'asignaciones': asignaciones,
    })

@docente_required
def calificaciones_docente_view(request):
    docente = request.user
    periodos = PeriodoAcademico.objects.filter(
        asignaciones__docente=docente,
        asignaciones__activa=True
    ).distinct().order_by('-activo', '-nombre')

    if not periodos.exists():
        periodos = PeriodoAcademico.objects.order_by('-activo', '-nombre')

    return render(request, 'docentes/calificaciones_docente.html', {
        'docente': docente,
        'periodos': periodos,
    })

@docente_required
def planificacion_docente_view(request):
    docente = request.user
    periodos = PeriodoAcademico.objects.filter(
        asignaciones__docente=docente,
        asignaciones__activa=True
    ).distinct().order_by('-activo', '-nombre')

    if not periodos.exists():
        periodos = PeriodoAcademico.objects.order_by('-activo', '-nombre')

    return render(request, 'docentes/planificacion_docente.html', {
        'docente': docente,
        'periodos': periodos,
    })


# ─── APIs JSON ────────────────────────────────────────────────────────────────

MAPA_GRADOS = {
    1: '1er Año', 2: '2do Año', 3: '3er Año', 
    4: '4to Año', 5: '5to Año'
}


@login_required
def api_secciones_docente(request):
    periodo_id = request.GET.get('periodo_id')
    if not periodo_id:
        return JsonResponse({'error': 'Periodo requerido'}, status=400)

    if request.user.rol == 'DOCENTE':
        asignaciones = AsignacionDocente.objects.filter(
            docente=request.user, periodo_id=periodo_id, activa=True
        )
    else:
        asignaciones = AsignacionDocente.objects.filter(
            periodo_id=periodo_id, activa=True
        )
    asignaciones = asignaciones.values('ano_grado', 'seccion').distinct().order_by('ano_grado', 'seccion')

    data = []
    seen = set()
    for a in asignaciones:
        key = (a['ano_grado'], a['seccion'])
        if key not in seen:
            seen.add(key)
            data.append({
                'ano_grado': a['ano_grado'],
                'seccion': a['seccion'],
                'label': f"{MAPA_GRADOS.get(a['ano_grado'], str(a['ano_grado']))} – Sección {a['seccion']}"
            })
    return JsonResponse({'secciones': data})


@login_required
def api_materias_docente(request):
    periodo_id = request.GET.get('periodo_id')
    ano_grado = request.GET.get('ano_grado')
    seccion = request.GET.get('seccion')

    if not all([periodo_id, ano_grado, seccion]):
        return JsonResponse({'error': 'Parámetros incompletos'}, status=400)

    if request.user.rol == 'DOCENTE':
        asignaciones = AsignacionDocente.objects.filter(
            docente=request.user,
            periodo_id=periodo_id,
            ano_grado=int(ano_grado),
            seccion=seccion,
            activa=True
        )
    else:
        asignaciones = AsignacionDocente.objects.filter(
            periodo_id=periodo_id,
            ano_grado=int(ano_grado),
            seccion=seccion,
            activa=True
        )
    asignaciones = asignaciones.select_related('asignatura')

    # Ensure uniqueness of materias
    data = []
    seen_subjs = set()
    for a in asignaciones:
        if a.asignatura.id not in seen_subjs:
            seen_subjs.add(a.asignatura.id)
            data.append({'id': a.asignatura.id, 'nombre': a.asignatura.nombre})
    return JsonResponse({'materias': data})


@login_required
def api_estudiantes_seccion(request):
    periodo_id = request.GET.get('periodo_id')
    ano_grado = request.GET.get('ano_grado')
    seccion = request.GET.get('seccion')
    asignatura_id = request.GET.get('asignatura_id')

    if not all([periodo_id, ano_grado, seccion, asignatura_id]):
        return JsonResponse({'error': 'Parámetros incompletos'}, status=400)

    # Obtener estudiantes almacenados en el expediente que pertenezcan a este año y sección
    estudiantes = Estudiante.objects.filter(
        ano_cursando=int(ano_grado),
        seccion=seccion,
        activo=True
    ).order_by('apellidos', 'nombres')

    # Garantizar que todos tengan una inscripción en este periodo para poder recibir notas
    for estudiante in estudiantes:
        Inscripcion.objects.get_or_create(
            estudiante=estudiante,
            periodo_id=periodo_id,
            defaults={'ano_grado': int(ano_grado), 'seccion': seccion}
        )

    cierre = PeriodoCierre.objects.filter(
        asignatura_id=asignatura_id, periodo_id=periodo_id, seccion=seccion
    ).first()

    data = []
    for e in estudiantes:
        data.append({
            'estudiante_id': e.id,
            'cedula': e.cedula_identidad,
            'nombre': f"{e.apellidos}, {e.nombres}",
        })

    return JsonResponse({
        'estudiantes': data,
        'cerrado': cierre.cerrado if cierre else False,
    })


@login_required
def api_buscar_estudiantes_gestion(request):
    """Busca estudiantes en el módulo de Expedientes para agregarlos manualmente."""
    query = request.GET.get('q', '').strip()
    ano_grado = request.GET.get('ano_grado')
    
    if not query or not ano_grado:
        return JsonResponse({'estudiantes': []})

    estudiantes = Estudiante.objects.filter(
        Q(nombres__icontains=query) |
        Q(apellidos__icontains=query) |
        Q(cedula_identidad__icontains=query),
        ano_cursando=int(ano_grado),
        activo=True
    ).order_by('apellidos', 'nombres')[:10] # Límite de 10 para rapidez

    data = [{
        'id': e.id,
        'cedula': e.cedula_identidad,
        'nombre': f"{e.apellidos}, {e.nombres}"
    } for e in estudiantes]

    return JsonResponse({'estudiantes': data})



@login_required
def api_evaluaciones_asignatura(request):
    asignatura_id = request.GET.get('asignatura_id')
    periodo_id = request.GET.get('periodo_id')
    seccion = request.GET.get('seccion')

    if not all([asignatura_id, periodo_id, seccion]):
        return JsonResponse({'error': 'Parámetros incompletos'}, status=400)

    evaluaciones = Evaluacion.objects.filter(
        asignatura_id=asignatura_id, periodo_id=periodo_id, seccion=seccion, activa=True
    ).order_by('fecha_creacion')

    notas_qs = NotaEvaluacion.objects.filter(
        evaluacion__asignatura_id=asignatura_id,
        evaluacion__periodo_id=periodo_id,
        evaluacion__seccion=seccion,
    ).select_related('inscripcion').values(
        'inscripcion__estudiante_id', 'evaluacion_id', 'nota', 'es_borrador', 'asistencia', 'observacion'
    )

    notas_map = {}
    for n in notas_qs:
        notas_map[f"{n['inscripcion__estudiante_id']}_{n['evaluacion_id']}"] = {
            'nota': n['nota'],
            'es_borrador': n['es_borrador'],
            'asistencia': n['asistencia'],
            'observacion': n['observacion'],
        }

    suma = evaluaciones.aggregate(s=Sum('ponderacion'))['s'] or 0

    evals_data = [{
        'id': ev.id,
        'nombre': ev.nombre,
        'tipo': ev.get_tipo_display(),
        'ponderacion': float(ev.ponderacion),
    } for ev in evaluaciones]

    return JsonResponse({
        'evaluaciones': evals_data,
        'notas': notas_map,
        'suma_ponderacion': float(suma),
    })


@login_required
@csrf_exempt
def api_crear_evaluacion(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    asignatura_id = data.get('asignatura_id')
    periodo_id = data.get('periodo_id')
    seccion = data.get('seccion', 'U')
    nombre = str(data.get('nombre', '')).strip()
    tipo = data.get('tipo', 'EXAMEN')
    try:
        ponderacion = float(data.get('ponderacion', 0))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Ponderación inválida'}, status=400)

    if not all([asignatura_id, periodo_id, nombre]):
        return JsonResponse({'error': 'Campos requeridos incompletos'}, status=400)
    if not (0 < ponderacion <= 100):
        return JsonResponse({'error': 'La ponderación debe estar entre 1 y 100'}, status=400)

    suma_actual = Evaluacion.suma_ponderacion(asignatura_id, periodo_id, seccion)
    if suma_actual + ponderacion > 100:
        disponible = 100 - suma_actual
        return JsonResponse({
            'error': f'Excedería el 100%. Disponible: {disponible:.1f}%'
        }, status=400)

    if PeriodoCierre.objects.filter(asignatura_id=asignatura_id, periodo_id=periodo_id, seccion=seccion, cerrado=True).exists():
        return JsonResponse({'error': 'Período cerrado. Contacte al administrador.'}, status=403)

    ev = Evaluacion.objects.create(
        asignatura_id=asignatura_id, periodo_id=periodo_id, seccion=seccion,
        nombre=nombre, tipo=tipo, ponderacion=ponderacion, creado_por=request.user
    )

    asignatura = Asignatura.objects.get(id=asignatura_id)
    lanzar_alerta_operativa(
        titulo=f'Nueva evaluación creada: {nombre}',
        mensaje=f'Docente {request.user.username} creó la evaluación "{nombre}" ({ponderacion}%) en {asignatura.nombre} – Sección {seccion}.',
        nivel_riesgo='INFORMATIVO',
        modulo='Notas Docentes',
        agrupacion_hash=f'ev-nueva-{asignatura_id}-{periodo_id}-{seccion}'
    )

    return JsonResponse({
        'ok': True,
        'evaluacion': {
            'id': ev.id, 'nombre': ev.nombre,
            'tipo': ev.get_tipo_display(), 'ponderacion': float(ev.ponderacion)
        },
        'suma_ponderacion': Evaluacion.suma_ponderacion(asignatura_id, periodo_id, seccion),
    })

@login_required
@csrf_exempt
def api_guardar_nota_estudiante(request):
    """Guarda la nota, asistencia y observación de un estudiante individual."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    inscripcion_id = data.get('inscripcion_id')
    evaluacion_id = data.get('evaluacion_id')
    nota_str = data.get('nota')
    asistencia = data.get('asistencia', True)
    observacion = str(data.get('observacion', '')).strip()[:1000] # Limitar a 1000 caracteres
    es_borrador = data.get('es_borrador', False)

    if not all([inscripcion_id, evaluacion_id]) or nota_str is None:
        return JsonResponse({'error': 'Faltan datos obligatorios'}, status=400)

    try:
        nota = float(nota_str)
    except ValueError:
        return JsonResponse({'error': 'La calificación debe ser un número válido'}, status=400)

    if not (0 <= nota <= 20):
        return JsonResponse({'error': 'La calificación debe estar entre 0 y 20'}, status=400)

    try:
        evaluacion = Evaluacion.objects.get(id=evaluacion_id)
        inscripcion = Inscripcion.objects.select_related('estudiante').get(id=inscripcion_id)
    except (Evaluacion.DoesNotExist, Inscripcion.DoesNotExist):
        return JsonResponse({'error': 'Evaluación o Estudiante no encontrado'}, status=404)

    if PeriodoCierre.objects.filter(
        asignatura_id=evaluacion.asignatura_id, 
        periodo_id=evaluacion.periodo_id, 
        seccion=evaluacion.seccion, 
        cerrado=True
    ).exists():
        return JsonResponse({'error': 'Período cerrado. No se pueden guardar notas.'}, status=403)

    obj, created = NotaEvaluacion.objects.update_or_create(
        inscripcion_id=inscripcion_id,
        evaluacion_id=evaluacion_id,
        defaults={
            'nota': nota, 
            'asistencia': asistencia,
            'observacion': observacion,
            'es_borrador': es_borrador, 
            'registrado_por': request.user
        }
    )

    if nota < 10:
        lanzar_alerta_operativa(
            titulo=f'Nota baja: {inscripcion.estudiante.apellidos}',
            mensaje=f'Estudiante {inscripcion.estudiante.nombres} {inscripcion.estudiante.apellidos} (V-{inscripcion.estudiante.cedula_identidad}) obtuvo {nota}/20 en "{evaluacion.nombre}".',
            nivel_riesgo='ADVERTENCIA',
            modulo='Notas Docentes',
            agrupacion_hash=f'nota-baja-{inscripcion_id}-{evaluacion_id}'
        )

    # Retornar datos del estudiante para actualizar la UI
    e = inscripcion.estudiante
    return JsonResponse({
        'ok': True, 
        'mensaje': 'Calificación guardada correctamente',
        'estudiante': {
            'inscripcion_id': inscripcion.id,
            'cedula': e.cedula_identidad,
            'nombre': f"{e.apellidos}, {e.nombres}",
            'nota': nota,
            'asistencia': asistencia,
            'observacion': observacion
        }
    })



@login_required
@csrf_exempt
def api_guardar_notas(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    notas = data.get('notas', [])   # [{inscripcion_id, evaluacion_id, nota}]
    es_borrador = data.get('es_borrador', True)
    asignatura_id = data.get('asignatura_id')
    periodo_id = data.get('periodo_id')
    seccion = data.get('seccion', 'U')

    if PeriodoCierre.objects.filter(
        asignatura_id=asignatura_id, periodo_id=periodo_id, seccion=seccion, cerrado=True
    ).exists():
        return JsonResponse({'error': 'Período cerrado. No se pueden guardar notas.'}, status=403)

    guardadas = 0
    errores = []
    for item in notas:
        try:
            est_id = int(item['estudiante_id'])
            eval_id = int(item['evaluacion_id'])
            nota = float(item['nota'])
            asistencia = item.get('asistencia', True)
            observacion = str(item.get('observacion', '')).strip()[:1000]
        except (KeyError, ValueError, TypeError):
            errores.append(str(item))
            continue

        if not (0 <= nota <= 20):
            errores.append(f'Nota fuera de rango (0-20): {nota}')
            continue

        # Asegurar que existe la inscripción (Lazy Enrollment)
        insc, _ = Inscripcion.objects.get_or_create(
            estudiante_id=est_id,
            periodo_id=periodo_id,
            defaults={'ano_grado': int(data.get('ano_grado', 1)), 'seccion': seccion}
        )

        obj, created = NotaEvaluacion.objects.update_or_create(
            inscripcion_id=insc.id,
            evaluacion_id=eval_id,
            defaults={
                'nota': nota, 
                'asistencia': asistencia,
                'observacion': observacion,
                'es_borrador': es_borrador, 
                'registrado_por': request.user
            }
        )
        guardadas += 1

        # Alerta si nota crítica
        if nota < 10:
            est = Estudiante.objects.get(id=est_id)
            ev = Evaluacion.objects.get(id=eval_id)
            lanzar_alerta_operativa(
                titulo=f'Nota baja: {est.apellidos}',
                mensaje=f'Estudiante {est.nombres} {est.apellidos} (V-{est.cedula_identidad}) obtuvo {nota}/20 en "{ev.nombre}".',
                nivel_riesgo='ADVERTENCIA',
                modulo='Notas Docentes',
                agrupacion_hash=f'nota-baja-{est_id}-{eval_id}'
            )

    if guardadas > 0:
        lanzar_alerta_operativa(
            titulo='Notas registradas',
            mensaje=f'Docente {request.user.username} {"guardó borrador" if es_borrador else "confirmó definitivamente"} {guardadas} nota(s) en sección {seccion}.',
            nivel_riesgo='INFORMATIVO',
            modulo='Notas Docentes',
            agrupacion_hash=f'notas-{request.user.id}-{asignatura_id}-{periodo_id}-{seccion}'
        )
        
        from auditoria.models import registrar_evento
        registrar_evento(
            tipo='MODIFICACION' if es_borrador else 'CREACION',
            descripcion=f'Se {"guardaron en borrador" if es_borrador else "confirmaron definitivamente"} {guardadas} notas de la sección {seccion}.',
            modulo='Calificaciones',
            usuario=request.user.username,
            nivel_riesgo='MEDIO' if not es_borrador else 'INFORMATIVO'
        )

    return JsonResponse({'ok': True, 'guardadas': guardadas, 'errores': errores})


@login_required
@csrf_exempt
def api_cerrar_periodo(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    asignatura_id = data.get('asignatura_id')
    periodo_id = data.get('periodo_id')
    seccion = data.get('seccion', 'U')

    if not all([asignatura_id, periodo_id]):
        return JsonResponse({'error': 'Parámetros requeridos'}, status=400)

    cierre, _ = PeriodoCierre.objects.get_or_create(
        asignatura_id=asignatura_id, periodo_id=periodo_id, seccion=seccion
    )
    cierre.cerrado = True
    cierre.cerrado_por = request.user
    cierre.fecha_cierre = now()
    cierre.save()

    asignatura = Asignatura.objects.get(id=asignatura_id)
    lanzar_alerta_operativa(
        titulo=f'Período cerrado: {asignatura.nombre}',
        mensaje=f'Docente {request.user.username} cerró el período de evaluaciones para {asignatura.nombre} – Sección {seccion}. No se admitirán más cambios.',
        nivel_riesgo='CRITICO',
        modulo='Notas Docentes',
    )

    return JsonResponse({'ok': True, 'cerrado': True})


# ═══════════════════════════════════════════════════════════════════════════════
# MÓDULO ADMINISTRATIVO — Gestión de Docentes
# ═══════════════════════════════════════════════════════════════════════════════

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from .models import PerfilDocente, ESTADOS_VENEZUELA


@login_required
def gestion_docentes_view(request):
    """Lista de todos los usuarios con rol DOCENTE — acceso administrativo."""
    Usuario = get_user_model()
    query = request.GET.get('q', '').strip()
    docentes = Usuario.objects.filter(rol='DOCENTE').order_by('username')
    if query:
        docentes = docentes.filter(
            Q(username__icontains=query) |
            Q(nombre_completo__icontains=query)
        )

    # Enriquecer con conteo de asignaciones y notas
    datos = []
    for d in docentes:
        asignaciones = AsignacionDocente.objects.filter(docente=d, activa=True)
        notas_count = NotaEvaluacion.objects.filter(registrado_por=d).count()
        perfil = getattr(d, 'perfil_docente', None)
        datos.append({
            'usuario': d,
            'perfil': perfil,
            'asignaciones_count': asignaciones.count(),
            'notas_count': notas_count,
            'asignaciones_preview': list(
                asignaciones.values('ano_grado', 'seccion', 'asignatura__nombre')[:3]
            ),
        })

    return render(request, 'docentes/gestion_docentes.html', {
        'datos': datos,
        'query': query,
        'total': len(datos),
    })


@login_required
def perfil_docente_admin_view(request, docente_id):
    """Perfil completo de un docente — datos personales + asignaciones."""
    Usuario = get_user_model()
    docente = get_object_or_404(Usuario, id=docente_id, rol='DOCENTE')
    perfil, _ = PerfilDocente.objects.get_or_create(usuario=docente)
    asignaciones = AsignacionDocente.objects.filter(
        docente=docente, activa=True
    ).select_related('asignatura', 'periodo').order_by('ano_grado', 'seccion')
    asignaturas_disponibles = Asignatura.objects.all().order_by('nombre')
    periodos = PeriodoAcademico.objects.all().order_by('-activo', '-nombre')
    periodo_activo = PeriodoAcademico.objects.filter(activo=True).first() or periodos.first()

    MAPA = {
        11: '1er Grado', 12: '2do Grado', 13: '3er Grado', 
        14: '4to Grado', 15: '5to Grado', 16: '6to Grado',
        1: '1er Año', 2: '2do Año', 3: '3er Año', 
        4: '4to Año', 5: '5to Año'
    }

    return render(request, 'docentes/perfil_docente_admin.html', {
        'docente': docente,
        'perfil': perfil,
        'asignaciones': asignaciones,
        'asignaturas_disponibles': asignaturas_disponibles,
        'periodos': periodos,
        'periodo_activo': periodo_activo,
        'estados_venezuela': ESTADOS_VENEZUELA,
        'mapa_grados': MAPA,
    })


@login_required
def api_asignaciones_docente(request, docente_id):
    """Devuelve las asignaciones activas de un docente (para vista administrativa)."""
    Usuario = get_user_model()
    try:
        docente = Usuario.objects.get(id=docente_id, rol='DOCENTE')
    except Usuario.DoesNotExist:
        return JsonResponse({'error': 'Docente no encontrado'}, status=404)

    asignaciones = AsignacionDocente.objects.filter(
        docente=docente, activa=True
    ).select_related('asignatura', 'periodo').order_by('-periodo__nombre', 'ano_grado', 'seccion')

    data = []
    for a in asignaciones:
        data.append({
            'id': a.id,
            'asignatura_id': a.asignatura.id,
            'asignatura_nombre': a.asignatura.nombre,
            'periodo_id': a.periodo.id,
            'periodo_nombre': a.periodo.nombre,
            'ano_grado': a.ano_grado,
            'seccion': a.seccion,
        })
    return JsonResponse({'asignaciones': data})


@login_required
@csrf_exempt
def api_guardar_perfil_docente(request):
    """Guarda/actualiza los datos personales y la foto de perfil del PerfilDocente."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
        
    if request.content_type.startswith('multipart/form-data'):
        data = request.POST
    else:
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

    docente_id = data.get('docente_id')
    if not docente_id:
        return JsonResponse({'error': 'docente_id requerido'}, status=400)

    Usuario = get_user_model()
    try:
        docente = Usuario.objects.get(id=docente_id, rol='DOCENTE')
    except Usuario.DoesNotExist:
        return JsonResponse({'error': 'Docente no encontrado'}, status=404)

    perfil, _ = PerfilDocente.objects.get_or_create(usuario=docente)
    
    cedula = str(data.get('cedula', '')).strip()
    if not cedula:
        return JsonResponse({'error': 'La cédula es obligatoria'}, status=400)
    if not cedula.isdigit():
        return JsonResponse({'error': 'La cédula debe contener solo números'}, status=400)
    
    # Validar duplicados
    if PerfilDocente.objects.filter(cedula=cedula).exclude(usuario=docente).exists():
        return JsonResponse({'error': 'Esta cédula ya está registrada para otro docente'}, status=400)

    perfil.cedula = cedula
    perfil.nombre = data.get('nombre', perfil.nombre).strip()
    perfil.apellidos = data.get('apellidos', perfil.apellidos).strip()
    perfil.email = data.get('email', perfil.email).strip()
    perfil.telefono = data.get('telefono', perfil.telefono).strip()
    estado = data.get('estado_residencia', perfil.estado_residencia)
    codigos_validos = [e[0] for e in ESTADOS_VENEZUELA]
    perfil.estado_residencia = estado if estado in codigos_validos else perfil.estado_residencia
    
    if 'foto_perfil' in request.FILES:
        perfil.foto_perfil = request.FILES['foto_perfil']

    perfil.save()

    # Actualizar nombre_completo en Usuario también
    if perfil.nombre and perfil.apellidos:
        docente.nombre_completo = f"{perfil.nombre} {perfil.apellidos}"
        docente.save(update_fields=['nombre_completo'])

    # Sincronizar con PerfilAdministrativo si existe
    try:
        from usuarios.models import PerfilAdministrativo
        perf_admin, _ = PerfilAdministrativo.objects.get_or_create(usuario=docente)
        perf_admin.nombres = perfil.nombre
        perf_admin.apellidos = perfil.apellidos
        perf_admin.cedula = perfil.cedula
        perf_admin.email = perfil.email
        perf_admin.telefono = perfil.telefono
        perf_admin.cargo = "Docente"
        perf_admin.save()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error al sincronizar PerfilAdministrativo desde perfil docente: {e}", exc_info=True)

    # Sincronizar con el modelo Personal de pagos si existe por cédula o correo
    try:
        from pagos.models import Personal
        personal_obj = None
        if perfil.cedula:
            personal_obj = Personal.objects.filter(cedula=perfil.cedula).first()
        if not personal_obj and perfil.email:
            personal_obj = Personal.objects.filter(correo__iexact=perfil.email).first()
            
        if personal_obj:
            personal_obj.nombre_completo = f"{perfil.nombre} {perfil.apellidos}".strip() or personal_obj.nombre_completo
            personal_obj.telefono = perfil.telefono or personal_obj.telefono
            personal_obj.correo = perfil.email or personal_obj.correo
            personal_obj.cargo = "Docente"
            personal_obj.save()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error al sincronizar Personal desde perfil docente: {e}", exc_info=True)

    return JsonResponse({'ok': True, 'nombre_completo': perfil.nombre_completo})


@login_required
@csrf_exempt
def api_gestionar_asignacion(request):
    """Crea, edita o elimina una AsignacionDocente desde el panel admin."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    accion = data.get('accion')  # 'crear' | 'editar' | 'eliminar'
    docente_id = data.get('docente_id')

    Usuario = get_user_model()
    try:
        docente = Usuario.objects.get(id=docente_id, rol='DOCENTE')
    except Usuario.DoesNotExist:
        return JsonResponse({'error': 'Docente no encontrado'}, status=404)

    if accion == 'crear':
        ano_grado = data.get('ano_grado')
        seccion = str(data.get('seccion', '')).upper().strip()
        asignatura_id = data.get('asignatura_id')

        if not all([ano_grado, seccion, asignatura_id]):
            return JsonResponse({'error': 'Año, Sección y Materia son obligatorios'}, status=400)
        if not seccion.isalpha() or len(seccion) != 1:
            return JsonResponse({'error': 'La sección debe ser una sola letra'}, status=400)

        periodo = PeriodoAcademico.objects.filter(activo=True).first()
        if not periodo:
            periodo = PeriodoAcademico.objects.order_by('-activo', '-nombre').first()
        if not periodo:
            return JsonResponse({'error': 'No hay período académico configurado'}, status=400)

        # Validar si este docente u otro ya tiene esta asignación activa
        if AsignacionDocente.objects.filter(
            asignatura_id=asignatura_id,
            periodo=periodo,
            ano_grado=int(ano_grado),
            seccion=seccion,
            activa=True
        ).exists():
            return JsonResponse({'error': 'Ya existe un docente asignado a esta materia en esta sección.'}, status=400)

        asig, created = AsignacionDocente.objects.get_or_create(
            docente=docente,
            asignatura_id=asignatura_id,
            periodo=periodo,
            ano_grado=int(ano_grado),
            seccion=seccion,
            defaults={'activa': True}
        )
        if not created:
            asig.activa = True
            asig.save()

        return JsonResponse({
            'ok': True,
            'creada': created,
            'asignacion': {
                'id': asig.id,
                'ano_grado': asig.ano_grado,
                'seccion': asig.seccion,
                'materia': asig.asignatura.nombre,
                'asignatura_id': asig.asignatura.id,
                'periodo': asig.periodo.nombre,
                'label': f"{asig.ano_grado}{asig.seccion} · {asig.asignatura.nombre}",
            }
        })

    elif accion == 'editar':
        asig_id = data.get('asignacion_id')
        try:
            asig = AsignacionDocente.objects.get(id=asig_id, docente=docente)
        except AsignacionDocente.DoesNotExist:
            return JsonResponse({'error': 'Asignación no encontrada'}, status=404)

        ano_grado = data.get('ano_grado', asig.ano_grado)
        seccion = str(data.get('seccion', asig.seccion)).upper().strip()
        asignatura_id = data.get('asignatura_id', asig.asignatura_id)

        if seccion and (not seccion.isalpha() or len(seccion) != 1):
            return JsonResponse({'error': 'La sección debe ser una sola letra'}, status=400)

        asig.ano_grado = int(ano_grado)
        asig.seccion = seccion
        asig.asignatura_id = asignatura_id
        asig.save()

        return JsonResponse({
            'ok': True,
            'asignacion': {
                'id': asig.id,
                'ano_grado': asig.ano_grado,
                'seccion': asig.seccion,
                'materia': asig.asignatura.nombre,
                'asignatura_id': asig.asignatura_id,
                'label': f"{asig.ano_grado}{asig.seccion} · {asig.asignatura.nombre}",
            }
        })

    elif accion == 'eliminar':
        asig_id = data.get('asignacion_id')
        try:
            asig = AsignacionDocente.objects.get(id=asig_id, docente=docente)
            asig.activa = False
            asig.save()
            return JsonResponse({'ok': True, 'eliminada': asig_id})
        except AsignacionDocente.DoesNotExist:
            return JsonResponse({'error': 'Asignación no encontrada'}, status=404)

    elif accion == 'restablecer_todas':
        if request.user.rol != 'ADMINISTRATIVO' and request.user.rol != 'DESARROLLADOR':
            return JsonResponse({'error': 'No tienes permisos para realizar esta acción.'}, status=403)
        
        asignaciones = AsignacionDocente.objects.filter(docente=docente, activa=True)
        count = asignaciones.count()
        asignaciones.update(activa=False)
        return JsonResponse({'ok': True, 'mensaje': f'{count} materias restablecidas.'})

    return JsonResponse({'error': f'Acción desconocida: {accion}'}, status=400)


@login_required
def api_materias_disponibles(request):
    """Retorna todas las asignaturas disponibles en la BD (sin duplicados aparentes)."""
    import unicodedata
    def normalize_str(s):
        s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
        s = s.upper()
        # Remove common punctuation and spaces
        for char in ['.', '/', '-', ' ']:
            s = s.replace(char, '')
        if s == 'MATEMATICAS':
            s = 'MATEMATICA'
        return s
        
    asignaturas = Asignatura.objects.all().order_by('nombre').values('id', 'nombre', 'codigo', 'ano_grado')
    
    seen = set()
    unique_asignaturas = []
    for asig in asignaturas:
        norm_name = normalize_str(asig['nombre'])
        key = f"{norm_name}_{asig['ano_grado']}"
        if key not in seen:
            seen.add(key)
            unique_asignaturas.append(asig)
            
    return JsonResponse({'materias': unique_asignaturas})


# ═══════════════════════════════════════════════════════════════════════════════
# PORTAL DOCENTE — API mejorada: Combinaciones unificadas
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def api_combinaciones_docente(request):
    """Retorna combinaciones únicas año+sección del docente (para selector unificado en portal)."""
    periodo_id = request.GET.get('periodo_id')
    if not periodo_id:
        return JsonResponse({'error': 'Periodo requerido'}, status=400)

    if request.user.rol == 'DOCENTE':
        asignaciones = AsignacionDocente.objects.filter(
            docente=request.user, periodo_id=periodo_id, activa=True
        )
    else:
        asignaciones = AsignacionDocente.objects.filter(
            periodo_id=periodo_id, activa=True
        )
    asignaciones = asignaciones.values('ano_grado', 'seccion').distinct().order_by('ano_grado', 'seccion')

    MAPA = {
        11: '1er Grado', 12: '2do Grado', 13: '3er Grado', 
        14: '4to Grado', 15: '5to Grado', 16: '6to Grado',
        1: '1er Año', 2: '2do Año', 3: '3er Año', 
        4: '4to Año', 5: '5to Año'
    }
    data, seen = [], set()
    for a in asignaciones:
        key = (a['ano_grado'], a['seccion'])
        if key not in seen:
            seen.add(key)
            data.append({
                'valor': f"{a['ano_grado']}-{a['seccion']}",
                'ano_grado': a['ano_grado'],
                'seccion': a['seccion'],
                'label': f"{MAPA.get(a['ano_grado'], str(a['ano_grado']))} – Sección {a['seccion']}",
            })
    return JsonResponse({'combinaciones': data})


@login_required
def api_materias_por_combinacion(request):
    """Retorna materias asignadas a una combinación año+sección del docente."""
    periodo_id = request.GET.get('periodo_id')
    ano_grado = request.GET.get('ano_grado')
    seccion = request.GET.get('seccion')

    if not all([periodo_id, ano_grado, seccion]):
        return JsonResponse({'error': 'Parámetros incompletos'}, status=400)

    if request.user.rol == 'DOCENTE':
        asignaciones = AsignacionDocente.objects.filter(
            docente=request.user,
            periodo_id=periodo_id,
            ano_grado=int(ano_grado),
            seccion=seccion,
            activa=True
        )
    else:
        asignaciones = AsignacionDocente.objects.filter(
            periodo_id=periodo_id,
            ano_grado=int(ano_grado),
            seccion=seccion,
            activa=True
        )
    asignaciones = asignaciones.select_related('asignatura')

    # Ensure uniqueness of materias
    data = []
    seen_subjs = set()
    for a in asignaciones:
        if a.asignatura.id not in seen_subjs:
            seen_subjs.add(a.asignatura.id)
            data.append({'id': a.asignatura.id, 'nombre': a.asignatura.nombre})
    return JsonResponse({'materias': data})




@login_required
@csrf_exempt
def api_eliminar_evaluaciones(request):
    """
    Elimina físicamente una o varias evaluaciones.
    Solo permitido para el rol ADMINISTRATIVO.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    if request.user.rol != 'ADMINISTRATIVO' and request.user.rol != 'DESARROLLADOR':
        return JsonResponse({'error': 'No tienes permisos para realizar esta acción.'}, status=403)
        
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
        
    evaluaciones_ids = data.get('evaluaciones_ids', [])
    if not evaluaciones_ids or not isinstance(evaluaciones_ids, list):
        return JsonResponse({'error': 'Debe proporcionar una lista de IDs de evaluaciones.'}, status=400)
        
    try:
        # Al eliminar evaluaciones, se eliminan en cascada las NotaEvaluacion asociadas (si está así en el modelo)
        # O podemos eliminarlas manualmente para estar seguros
        NotaEvaluacion.objects.filter(evaluacion_id__in=evaluaciones_ids).delete()
        eliminados, _ = Evaluacion.objects.filter(id__in=evaluaciones_ids).delete()
        
        return JsonResponse({
            'ok': True, 
            'mensaje': f'Se han eliminado {eliminados} evaluaciones correctamente.'
        })
    except Exception as e:
        return JsonResponse({'error': f'Error al eliminar: {str(e)}'}, status=500)

@login_required
def api_buscar_evaluaciones_admin(request):
    """Retorna evaluaciones según filtros para la gestión administrativa."""
    if request.user.rol not in ['ADMINISTRATIVO', 'PERSONAL', 'DESARROLLADOR']:
        return JsonResponse({'error': 'No autorizado'}, status=403)
        
    query = request.GET.get('q', '').strip()
    docente_id = request.GET.get('docente_id')
    ano_grado = request.GET.get('ano_grado')
    seccion = request.GET.get('seccion')
    
    evals = Evaluacion.objects.select_related('asignatura', 'periodo', 'creado_por').filter(activa=True)
    
    if query:
        evals = evals.filter(nombre__icontains=query)
    if docente_id:
        evals = evals.filter(creado_por_id=docente_id)
    if ano_grado:
        evals = evals.filter(asignatura__ano_grado=ano_grado)
    if seccion:
        evals = evals.filter(seccion=seccion)
        
    evals = evals.order_by('-fecha_creacion')[:50]
    
    data = [{
        'id': e.id,
        'nombre': e.nombre,
        'tipo': e.get_tipo_display(),
        'ponderacion': float(e.ponderacion),
        'asignatura': e.asignatura.nombre,
        'periodo': e.periodo.nombre,
        'seccion': e.seccion,
        'docente': e.creado_por.username if e.creado_por else 'N/A',
        'fecha': e.fecha_creacion.strftime('%d/%m/%Y')
    } for e in evals]
    
    return JsonResponse({'evaluaciones': data})

# ═══════════════════════════════════════════════════════════════════════════════
# PLANIFICACIÓN DOCENTE — APIs
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
def api_listar_temas(request):
    asignatura_id = request.GET.get('asignatura_id')
    periodo_id = request.GET.get('periodo_id')
    seccion = request.GET.get('seccion')

    if not all([asignatura_id, periodo_id, seccion]):
        return JsonResponse({'error': 'Parámetros incompletos'}, status=400)

    temas = TemaClase.objects.filter(
        asignatura_id=asignatura_id, periodo_id=periodo_id, seccion=seccion
    ).prefetch_related('materiales', 'tareas')

    data = []
    for t in temas:
        data.append({
            'id': t.id,
            'titulo': t.titulo,
            'descripcion': t.descripcion,
            'fecha_programada': t.fecha_programada.strftime('%Y-%m-%d') if t.fecha_programada else None,
            'materiales': [{'id': m.id, 'titulo': m.titulo, 'archivo': m.archivo.url if m.archivo else None, 'enlace': m.enlace} for m in t.materiales.all()],
            'tareas': [{'id': tr.id, 'titulo': tr.titulo, 'instrucciones': tr.instrucciones, 'fecha_entrega': tr.fecha_entrega.strftime('%Y-%m-%dT%H:%M') if tr.fecha_entrega else None} for tr in t.tareas.all()]
        })

    return JsonResponse({'temas': data})

@login_required
@csrf_exempt
def api_crear_tema(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    asignatura_id = data.get('asignatura_id')
    periodo_id = data.get('periodo_id')
    seccion = data.get('seccion')
    titulo = data.get('titulo')
    descripcion = data.get('descripcion', '')
    fecha_programada = data.get('fecha_programada')

    if not all([asignatura_id, periodo_id, seccion, titulo]):
        return JsonResponse({'error': 'Campos requeridos incompletos'}, status=400)

    tema = TemaClase.objects.create(
        asignatura_id=asignatura_id,
        periodo_id=periodo_id,
        seccion=seccion,
        titulo=titulo,
        descripcion=descripcion,
        fecha_programada=fecha_programada or None,
        creado_por=request.user
    )

    return JsonResponse({'ok': True, 'tema_id': tema.id})

@login_required
@csrf_exempt
def api_eliminar_tema(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    tema_id = data.get('tema_id')
    try:
        if request.user.rol == 'DOCENTE':
            tema = TemaClase.objects.get(id=tema_id, creado_por=request.user)
        else:
            tema = TemaClase.objects.get(id=tema_id)
        tema.delete()
        return JsonResponse({'ok': True})
    except TemaClase.DoesNotExist:
        return JsonResponse({'error': 'Tema no encontrado'}, status=404)

@login_required
@csrf_exempt
def api_subir_material(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    tema_id = request.POST.get('tema_id')
    titulo = request.POST.get('titulo')
    enlace = request.POST.get('enlace')
    archivo = request.FILES.get('archivo')

    if not tema_id or not titulo:
        return JsonResponse({'error': 'Campos requeridos incompletos'}, status=400)
        
    try:
        if request.user.rol == 'DOCENTE':
            tema = TemaClase.objects.get(id=tema_id, creado_por=request.user)
        else:
            tema = TemaClase.objects.get(id=tema_id)
    except TemaClase.DoesNotExist:
        return JsonResponse({'error': 'Tema no encontrado'}, status=404)

    material = MaterialApoyo.objects.create(
        tema=tema,
        titulo=titulo,
        enlace=enlace,
        archivo=archivo
    )

    return JsonResponse({'ok': True, 'material_id': material.id})

@login_required
@csrf_exempt
def api_eliminar_material(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    material_id = data.get('material_id')
    try:
        if request.user.rol == 'DOCENTE':
            material = MaterialApoyo.objects.get(id=material_id, tema__creado_por=request.user)
        else:
            material = MaterialApoyo.objects.get(id=material_id)
        material.delete()
        return JsonResponse({'ok': True})
    except MaterialApoyo.DoesNotExist:
        return JsonResponse({'error': 'Material no encontrado'}, status=404)

@login_required
@csrf_exempt
def api_crear_tarea(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    tema_id = data.get('tema_id')
    titulo = data.get('titulo')
    instrucciones = data.get('instrucciones', '')
    fecha_entrega = data.get('fecha_entrega')

    if not tema_id or not titulo:
        return JsonResponse({'error': 'Campos requeridos incompletos'}, status=400)
        
    try:
        if request.user.rol == 'DOCENTE':
            tema = TemaClase.objects.get(id=tema_id, creado_por=request.user)
        else:
            tema = TemaClase.objects.get(id=tema_id)
    except TemaClase.DoesNotExist:
        return JsonResponse({'error': 'Tema no encontrado'}, status=404)

    tarea = TareaDocente.objects.create(
        tema=tema,
        titulo=titulo,
        instrucciones=instrucciones,
        fecha_entrega=fecha_entrega or None
    )

    return JsonResponse({'ok': True, 'tarea_id': tarea.id})

@login_required
@csrf_exempt
def api_eliminar_tarea(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    tarea_id = data.get('tarea_id')
    try:
        if request.user.rol == 'DOCENTE':
            tarea = TareaDocente.objects.get(id=tarea_id, tema__creado_por=request.user)
        else:
            tarea = TareaDocente.objects.get(id=tarea_id)
        tarea.delete()
        return JsonResponse({'ok': True})
    except TareaDocente.DoesNotExist:
        return JsonResponse({'error': 'Tarea no encontrada'}, status=404)

@login_required
@csrf_exempt
def api_editar_tarea(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    tarea_id = data.get('tarea_id')
    titulo = data.get('titulo')
    instrucciones = data.get('instrucciones', '')
    fecha_entrega = data.get('fecha_entrega')

    if not tarea_id or not titulo:
        return JsonResponse({'error': 'Campos requeridos incompletos'}, status=400)
        
    try:
        if request.user.rol == 'DOCENTE':
            tarea = TareaDocente.objects.get(id=tarea_id, tema__creado_por=request.user)
        else:
            tarea = TareaDocente.objects.get(id=tarea_id)
            
        tarea.titulo = titulo
        tarea.instrucciones = instrucciones
        tarea.fecha_entrega = fecha_entrega or None
        tarea.save()
        return JsonResponse({'ok': True})
    except TareaDocente.DoesNotExist:
        return JsonResponse({'error': 'Tarea no encontrada'}, status=404)

@login_required
@csrf_exempt
def api_plan_evaluacion_flask(request, docente_id):
    """
    Vista proxy para obtener el plan de evaluación desde Flask.
    """
    asignatura_id = request.GET.get('asignatura_id')
    seccion = request.GET.get('seccion')

    if not asignatura_id:
        return JsonResponse({'error': 'Falta asignatura_id'}, status=400)

    import os
    # URL base de Flask: se lee del .env o usa la URL de producción en Vercel por defecto
    base_url = os.environ.get("PORTAL_DOCENTE_URL", "https://docente-apacuana.vercel.app").rstrip("/")
    flask_url = f"{base_url}/docente/api/planificacion/perfil_docente/{docente_id}/plan_evaluacion/{asignatura_id}?format=json"
    
    if seccion:
        flask_url += f"&seccion={seccion}"

    try:
        response = requests.get(flask_url, timeout=5)
        # Si el status es 4xx o 5xx, intentamos obtener el json de error de flask
        if not response.ok:
            try:
                error_data = response.json()
                return JsonResponse({'error': f"Flask devolvió error: {error_data.get('error', 'Desconocido')}"}, status=response.status_code)
            except Exception:
                return JsonResponse({'error': f"Flask devolvió status {response.status_code}"}, status=response.status_code)

        data = response.json()
        return JsonResponse(data)
    except requests.exceptions.RequestException as e:
        print("===== ERROR EN CONEXION DJANGO -> FLASK =====")
        traceback.print_exc()
        print("==============================================")
        return JsonResponse({'error': f"Error al contactar con el servidor Flask: {str(e)}"}, status=500)
    except Exception as e:
        print("===== ERROR INESPERADO =====")
        traceback.print_exc()
        print("============================")
        return JsonResponse({'error': f"Error inesperado: {str(e)}"}, status=500)

# ─── Gestión de Períodos Académicos ──────────────────────────────────────────

def gestion_periodos_view(request):
    """
    Vista principal para la gestión de Períodos Académicos.
    """
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Solo roles autorizados pueden ver esta página
    if request.user.rol not in ['DESARROLLADOR', 'DIRECTIVO', 'COORDINADOR', 'ADMINISTRATIVO']:
        return redirect('home')

    context = {
        'periodos': PeriodoAcademico.objects.all().order_by('-activo', '-fecha_inicio')
    }
    return render(request, 'docentes/gestion_periodos.html', context)


def api_periodos_list_create(request):
    """
    API sencilla para listar y crear periodos académicos.
    """
    if request.method == 'GET':
        periodos = PeriodoAcademico.objects.all().order_by('-activo', '-fecha_inicio')
        data = []
        for p in periodos:
            data.append({
                'id': p.id,
                'nombre': p.nombre,
                'fecha_inicio': p.fecha_inicio.strftime('%Y-%m-%d') if p.fecha_inicio else '',
                'fecha_fin': p.fecha_fin.strftime('%Y-%m-%d') if p.fecha_fin else '',
                'activo': p.activo,
            })
        return JsonResponse({'success': True, 'periodos': data})
        
    elif request.method == 'POST':
        if request.content_type == 'application/json':
            try:
                body = json.loads(request.body)
                nombre = body.get('nombre', '').strip()
                fecha_inicio = body.get('fecha_inicio', '').strip()
                fecha_fin = body.get('fecha_fin', '').strip()
                activo = body.get('activo', False)
            except Exception:
                return JsonResponse({'success': False, 'error': 'JSON inválido.'}, status=400)
        else:
            nombre = request.POST.get('nombre', '').strip()
            fecha_inicio = request.POST.get('fecha_inicio', '').strip()
            fecha_fin = request.POST.get('fecha_fin', '').strip()
            activo = request.POST.get('activo') == 'true' or request.POST.get('activo') == 'on' or request.POST.get('activo') is True

        if not nombre or not fecha_inicio or not fecha_fin:
            return JsonResponse({'success': False, 'error': 'Todos los campos son obligatorios.'}, status=400)

        # Validar único
        if PeriodoAcademico.objects.filter(nombre=nombre).exists():
            return JsonResponse({'success': False, 'error': 'Ya existe un período académico con ese nombre.'}, status=400)

        from datetime import datetime
        try:
            inicio_date = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
            fin_date = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Formato de fecha inválido. Debe ser AAAA-MM-DD.'}, status=400)

        try:
            if activo:
                # Desactivar otros períodos si este es activo
                PeriodoAcademico.objects.filter(activo=True).update(activo=False)
            
            p = PeriodoAcademico.objects.create(
                nombre=nombre,
                fecha_inicio=inicio_date,
                fecha_fin=fin_date,
                activo=activo
            )
            return JsonResponse({
                'success': True,
                'periodo': {
                    'id': p.id,
                    'nombre': p.nombre,
                    'fecha_inicio': p.fecha_inicio.strftime('%Y-%m-%d'),
                    'fecha_fin': p.fecha_fin.strftime('%Y-%m-%d'),
                    'activo': p.activo
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Error al guardar: {str(e)}'}, status=500)

    return JsonResponse({'success': False, 'error': 'Método no permitido.'}, status=405)


def api_periodo_update_delete(request, pk):
    """
    API sencilla para editar o eliminar un periodo académico.
    """
    try:
        p = PeriodoAcademico.objects.get(pk=pk)
    except PeriodoAcademico.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'El período académico no existe.'}, status=404)

    # Detectar si es una solicitud de eliminación (DELETE real o POST simulado)
    is_delete = (request.method == 'DELETE') or (request.method == 'POST' and request.POST.get('_method') == 'DELETE')

    if is_delete:
        try:
            if request.user.is_authenticated and request.user.rol == 'DESARROLLADOR':
                # Super-poder del Desarrollador: eliminar inscripciones asociadas en cascada para evitar el ProtectedError
                p.inscripciones.all().delete()
            p.delete()
            return JsonResponse({'success': True})
        except Exception:
            return JsonResponse({
                'success': False,
                'error': 'No se puede eliminar este período porque tiene inscripciones o notas asociadas.'
            }, status=400)

    # Si no es eliminación, procesar como actualización (edición)
    if request.method in ('POST', 'PUT'):
        if request.content_type == 'application/json':
            try:
                body = json.loads(request.body)
                nombre = body.get('nombre', '').strip()
                fecha_inicio = body.get('fecha_inicio', '').strip()
                fecha_fin = body.get('fecha_fin', '').strip()
                activo = body.get('activo', False)
            except Exception:
                return JsonResponse({'success': False, 'error': 'JSON inválido.'}, status=400)
        else:
            nombre = request.POST.get('nombre', '').strip()
            fecha_inicio = request.POST.get('fecha_inicio', '').strip()
            fecha_fin = request.POST.get('fecha_fin', '').strip()
            activo = request.POST.get('activo') == 'true' or request.POST.get('activo') == 'on' or request.POST.get('activo') is True

        if not nombre or not fecha_inicio or not fecha_fin:
            return JsonResponse({'success': False, 'error': 'Todos los campos son obligatorios.'}, status=400)

        # Validar único excepto a sí mismo
        if PeriodoAcademico.objects.filter(nombre=nombre).exclude(pk=pk).exists():
            return JsonResponse({'success': False, 'error': 'Ya existe otro período académico con ese nombre.'}, status=400)

        from datetime import datetime
        try:
            inicio_date = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
            fin_date = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Formato de fecha inválido. Debe ser AAAA-MM-DD.'}, status=400)

        try:
            if activo:
                # Desactivar otros períodos
                PeriodoAcademico.objects.filter(activo=True).exclude(pk=pk).update(activo=False)
            
            p.nombre = nombre
            p.fecha_inicio = inicio_date
            p.fecha_fin = fin_date
            p.activo = activo
            p.save()
            
            return JsonResponse({
                'success': True,
                'periodo': {
                    'id': p.id,
                    'nombre': p.nombre,
                    'fecha_inicio': p.fecha_inicio.strftime('%Y-%m-%d') if p.fecha_inicio else '',
                    'fecha_fin': p.fecha_fin.strftime('%Y-%m-%d') if p.fecha_fin else '',
                    'activo': p.activo
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Error al actualizar: {str(e)}'}, status=500)

    return JsonResponse({'success': False, 'error': 'Método no permitido.'}, status=405)


@require_POST
def api_cerrar_periodo(request):
    """
    Cierra el periodo activo y promueve a los estudiantes al siguiente grado/año.
    """
    from django.db import transaction
    
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'No autenticado.'}, status=401)
    if request.user.rol not in ['DESARROLLADOR', 'DIRECTIVO', 'COORDINADOR', 'ADMINISTRATIVO']:
        return JsonResponse({'success': False, 'error': 'No autorizado.'}, status=403)
        
    periodo = PeriodoAcademico.objects.filter(activo=True).first()
    if not periodo:
        return JsonResponse({'success': False, 'error': 'No hay un período activo para cerrar.'})

    try:
        with transaction.atomic():
            periodo.activo = False
            periodo.save()
            
            # Promover estudiantes activos
            estudiantes = Estudiante.objects.filter(activo=True)
            for est in estudiantes:
                if est.ano_cursando in [11, 12, 13, 14, 15]:
                    est.ano_cursando += 1
                elif est.ano_cursando == 16:
                    est.ano_cursando = 1  # Pasa a Secundaria 1er Año
                elif est.ano_cursando in [1, 2, 3, 4]:
                    est.ano_cursando += 1
                elif est.ano_cursando == 5:
                    est.ano_cursando = 6  # Pasa a Egresado
                
                est.save()

            lanzar_alerta_operativa('info', f'Período "{periodo.nombre}" cerrado y estudiantes promovidos (Primaria y Secundaria) por {request.user.username}.')

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error al promover estudiantes: {str(e)}'}, status=500)

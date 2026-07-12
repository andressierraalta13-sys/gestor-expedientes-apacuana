"""
Asistente Administrativo IA v2.0 - Contexto Rico con Nombres Reales
U.E.N. Colegio Apacuana

Mejoras v2.0:
  - Contexto específico con nombres reales (no solo conteos)
  - Acceso basado en rol: DOCENTE ve solo sus datos, ADMINISTRATIVO/PERSONAL ven todo
  - Detección de inconsistencias con nombres exactos (duplicados, sin asignación, etc.)
  - Prompt enriquecido para respuestas precisas y no genéricas

Gobernanza: Lectura y modificación permitidas. Eliminación física PROHIBIDA.
"""

import json
import logging
import os
from datetime import date

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.cache import cache

logger = logging.getLogger(__name__)

GEMINI_API_KEY = getattr(settings, 'GOOGLE_API_KEY', None) or os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY') or "AIzaSyArP6Vu5iQGIXcqBB6yqDAXB3FA4cgJklg"
MAX_ITEMS = 20  # Límite de elementos en listas del prompt


# ═══════════════════════════════════════════════════════════════════════════════
# CONTEXTO POR MÓDULO — Datos ricos con nombres reales
# ═══════════════════════════════════════════════════════════════════════════════

def _ctx_expedientes() -> dict:
    """Estudiantes: totales, distribución, listas de casos problemáticos con nombres."""
    try:
        from estudiantes.models import Estudiante, Expediente, ObservacionConductual

        dist = {}
        for i, label in [(1,'1er Año'),(2,'2do Año'),(3,'3er Año'),(4,'4to Año'),(5,'5to Año'),(6,'Egresados')]:
            # Contamos solo estudiantes con expediente para evitar contar "estudiantes fantasmas"
            c = Estudiante.objects.filter(expediente__isnull=False, ano_cursando=i).count()
            if c: dist[label] = c

        sin_exp = [
            f"{e.nombres} {e.apellidos} (V-{e.cedula_identidad})"
            for e in Estudiante.objects.filter(expediente__isnull=True)[:MAX_ITEMS]
        ]

        # Filtramos estudiante__isnull=False para evitar AttributeError con expedientes huérfanos
        incompletos = [
            f"{x.estudiante.nombres} {x.estudiante.apellidos} (V-{x.estudiante.cedula_identidad})"
            for x in Expediente.objects.filter(estudiante__isnull=False, estatus='INCOMPLETO').select_related('estudiante')[:MAX_ITEMS]
        ]

        # Para que coincida exactamente con el Resumen del Sistema del dashboard (solventes + incompletos)
        # pero filtrando huérfanos por seguridad y estabilidad en el chat
        solventes = Expediente.objects.filter(estudiante__isnull=False, estatus='SOLVENTE').count()
        incompletos_count = Expediente.objects.filter(estudiante__isnull=False, estatus='INCOMPLETO').count()

        return {
            'total': solventes + incompletos_count,
            'solventes': solventes,
            'incompletos_count': incompletos_count,
            'distribucion': dist,
            'sin_expediente': sin_exp,
            'incompletos_lista': incompletos,
            'total_observaciones': ObservacionConductual.objects.filter(estudiante__expediente__isnull=False).count(),
        }
    except Exception as e:
        logger.warning(f"[IA-ctx] expedientes: {e}")
        return {'error': str(e)}


def _ctx_docentes() -> dict:
    """Docentes: lista completa con nombres, asignaciones, estado y actividad de notas."""
    try:
        from django.contrib.auth import get_user_model
        from docentes.models import AsignacionDocente, NotaEvaluacion, PerfilDocente

        Usuario = get_user_model()
        lista = []
        for d in Usuario.objects.filter(rol='DOCENTE').order_by('username'):
            perfil = getattr(d, 'perfil_docente', None)
            nombre = (perfil.nombre_completo
                      if perfil and (perfil.nombre or perfil.apellidos)
                      else d.nombre_completo or d.username)
            asigs = list(AsignacionDocente.objects.filter(docente=d, activa=True)
                         .select_related('asignatura', 'periodo'))
            notas_confirmadas = NotaEvaluacion.objects.filter(registrado_por=d, es_borrador=False).count()
            notas_borrador    = NotaEvaluacion.objects.filter(registrado_por=d, es_borrador=True).count()
            lista.append({
                'username': d.username,
                'nombre': nombre,
                'activo': d.is_active,
                'email': perfil.email if perfil else '',
                'telefono': perfil.telefono if perfil else '',
                'asignaciones': [f"{a.ano_grado}{a.seccion}·{a.asignatura.nombre}({a.periodo.nombre})" for a in asigs],
                'notas_confirmadas': notas_confirmadas,
                'notas_borrador': notas_borrador,
                'falta_cedula': not (perfil and perfil.cedula),
            })

        sin_asig   = [d['nombre'] for d in lista if not d['asignaciones']]
        con_borrad = [f"{d['nombre']} ({d['notas_borrador']} borrador)" for d in lista if d['notas_borrador'] > 0]
        sin_cedula = [f"@{d['username']}" for d in lista if d['falta_cedula']]

        return {
            'total': len(lista),
            'lista': lista,
            'sin_asignacion': sin_asig,
            'con_notas_borrador': con_borrad,
            'sin_cedula': sin_cedula,
        }
    except Exception as e:
        logger.warning(f"[IA-ctx] docentes: {e}")
        return {'error': str(e)}



def _ctx_calificaciones() -> dict:
    """Calificaciones: período activo, asignaturas, notas por lapso."""
    try:
        from inscripciones.models import Inscripcion, Asignatura, PeriodoAcademico
        from calificaciones.models import Calificacion

        periodo_activo = PeriodoAcademico.objects.filter(activo=True).first()
        asignaturas = list(Asignatura.objects.values_list('nombre', flat=True).order_by('nombre')[:25])

        return {
            'periodo_activo': str(periodo_activo) if periodo_activo else 'Ninguno configurado',
            'total_periodos': PeriodoAcademico.objects.count(),
            'total_inscripciones': Inscripcion.objects.count(),
            'total_asignaturas': Asignatura.objects.count(),
            'asignaturas': asignaturas,
            'notas_L1': Calificacion.objects.filter(tipo='L1').count(),
            'notas_L2': Calificacion.objects.filter(tipo='L2').count(),
            'notas_L3': Calificacion.objects.filter(tipo='L3').count(),
            'notas_DEF': Calificacion.objects.filter(tipo='DEF').count(),
            'total_notas': Calificacion.objects.count(),
        }
    except Exception as e:
        logger.warning(f"[IA-ctx] calificaciones: {e}")
        return {'error': str(e)}


def _ctx_horarios() -> dict:
    """Horarios: totales y conflictos con nombres de docentes, e incluye horarios detallados."""
    try:
        from horarios.models import Horario, BloqueHorario, Aula
        from django.db.models import Count

        bloques = list(BloqueHorario.objects.all().select_related('horario', 'asignatura', 'docente'))
        
        conflictos_qs = (
            BloqueHorario.objects.filter(tipo='CLASE').exclude(docente_nombre='')
            .values('docente_nombre', 'dia_semana', 'hora_inicio')
            .annotate(n=Count('id')).filter(n__gt=1)
        )
        conflictos = [
            f"{c['docente_nombre']} — {c['dia_semana']} a las {c['hora_inicio']} ({c['n']} bloques solapados)"
            for c in conflictos_qs[:10]
        ]
        
        # Horarios Detallados por Docente y por Sección
        horarios_docentes = {}
        horarios_seccion = {}
        dias_map = {'1': 'Lun', '2': 'Mar', '3': 'Mié', '4': 'Jue', '5': 'Vie', '6': 'Sáb', '0': 'Dom'}
        for b in bloques:
            # Por docente
            nombre = b.docente_nombre
            if not nombre and b.docente:
                nombre = b.docente.get_full_name() or b.docente.username
            if not nombre:
                nombre = 'Sin Asignar'
                
            if nombre not in horarios_docentes:
                horarios_docentes[nombre] = {}
            dia = dias_map.get(b.dia_semana, b.dia_semana)
            if dia not in horarios_docentes[nombre]:
                horarios_docentes[nombre][dia] = []
            
            hora_rango = f"{b.hora_inicio.strftime('%H:%M')}-{b.hora_fin.strftime('%H:%M')}"
            
            if b.tipo != 'CLASE':
                desc = b.get_tipo_display()
            else:
                desc = b.asignatura.nombre if b.asignatura else 'Sin Materia'
                
            grado_sec = f"{b.horario.ano_grado}{b.horario.seccion}" if b.horario else ""
            horarios_docentes[nombre][dia].append(f"[{hora_rango} {desc} {grado_sec}]")
            
            # Por sección
            if grado_sec:
                if grado_sec not in horarios_seccion:
                    horarios_seccion[grado_sec] = {}
                if dia not in horarios_seccion[grado_sec]:
                    horarios_seccion[grado_sec][dia] = []
                horarios_seccion[grado_sec][dia].append(f"[{hora_rango} {desc} ({nombre})]")
            
        horarios_detallados = []
        for doc, dias in horarios_docentes.items():
            dias_str = ", ".join(f"{d}: {' '.join(sorted(clases))}" for d, clases in dias.items())
            horarios_detallados.append(f"• {doc} -> {dias_str}")
            
        horarios_por_seccion = []
        for sec, dias in horarios_seccion.items():
            dias_str = ", ".join(f"{d}: {' '.join(sorted(clases))}" for d, clases in dias.items())
            horarios_por_seccion.append(f"• {sec} -> {dias_str}")

        return {
            'total_horarios': Horario.objects.count(),
            'total_bloques': len(bloques),
            'bloques_clase': sum(1 for b in bloques if b.tipo == 'CLASE'),
            'total_aulas': Aula.objects.count(),
            'conflictos': conflictos,
            'detallados': horarios_detallados,
            'por_seccion': horarios_por_seccion,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[IA-ctx] horarios: {e}")
        return {'error': str(e)}

def _ctx_asistencias() -> dict:
    """Asistencia reciente del personal (Docentes/Administrativos)."""
    try:
        from asistencias.models import RegistroAsistencia
        from django.utils import timezone
        import datetime
        
        # Últimos 15 días
        start_date = timezone.now().date() - datetime.timedelta(days=15)
        registros = RegistroAsistencia.objects.filter(tipo='PERSONAL', fecha__gte=start_date).select_related('personal')
        
        asist_resumen = {}
        for r in registros:
            nombre = r.personal.get_full_name() if r.personal else f"ID {r.personal_id}"
            if not nombre.strip(): nombre = r.personal.username if r.personal else 'Desconocido'
            if nombre not in asist_resumen:
                asist_resumen[nombre] = {'asistencias': [], 'faltas': []}
            fecha_str = r.fecha.strftime('%d/%m/%Y')
            if r.asistio:
                asist_resumen[nombre]['asistencias'].append(fecha_str)
            else:
                asist_resumen[nombre]['faltas'].append(fecha_str)
                
        detalles = []
        for nombre, datos in asist_resumen.items():
            asist_str = f"Asistió: {', '.join(datos['asistencias'])}" if datos['asistencias'] else "Sin asistencias"
            faltas_str = f"Faltó: {', '.join(datos['faltas'])}" if datos['faltas'] else "Sin faltas"
            detalles.append(f"• {nombre}: {asist_str} | {faltas_str}")
            
        return {
            'resumen': detalles if detalles else ["Sin registros recientes de asistencia del personal."]
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[IA-ctx] asistencias: {e}")
        return {'error': str(e)}


def _ctx_usuarios() -> dict:
    """Usuarios del sistema: lista por rol, inactivos."""
    try:
        from django.contrib.auth import get_user_model
        Usuario = get_user_model()

        admins   = [f"{u.username} ({u.nombre_completo or 'sin nombre'})" for u in Usuario.objects.filter(rol='ADMINISTRATIVO')]
        personal = [f"{u.username} ({u.nombre_completo or 'sin nombre'})" for u in Usuario.objects.filter(rol='PERSONAL')]
        inactivos = [f"{u.username} [{u.rol}]" for u in Usuario.objects.filter(is_active=False)]

        return {
            'total': Usuario.objects.count(),
            'administrativos': admins,
            'personal': personal,
            'inactivos': inactivos,
        }
    except Exception as e:
        return {'error': str(e)}


def _ctx_docente_propio(user) -> dict:
    """Contexto exclusivo para un usuario con rol DOCENTE: solo sus propios datos."""
    try:
        from docentes.models import AsignacionDocente, NotaEvaluacion, PerfilDocente
        from inscripciones.models import Inscripcion

        perfil = getattr(user, 'perfil_docente', None)
        nombre = (perfil.nombre_completo
                  if perfil and (perfil.nombre or perfil.apellidos)
                  else user.nombre_completo or user.username)

        asigs = AsignacionDocente.objects.filter(docente=user, activa=True).select_related('asignatura', 'periodo')
        clases = []
        for a in asigs:
            n_estudiantes = Inscripcion.objects.filter(
                periodo=a.periodo, ano_grado=a.ano_grado, seccion=a.seccion
            ).count()
            n_notas_conf  = NotaEvaluacion.objects.filter(
                registrado_por=user, evaluacion__asignatura=a.asignatura,
                evaluacion__periodo=a.periodo, evaluacion__seccion=a.seccion, es_borrador=False
            ).count()
            n_notas_bor   = NotaEvaluacion.objects.filter(
                registrado_por=user, evaluacion__asignatura=a.asignatura,
                evaluacion__periodo=a.periodo, evaluacion__seccion=a.seccion, es_borrador=True
            ).count()
            clases.append(
                f"{a.ano_grado}{a.seccion} · {a.asignatura.nombre} ({a.periodo.nombre}) — "
                f"{n_estudiantes} estudiantes — Notas: {n_notas_conf} confirmadas, {n_notas_bor} borradores"
            )
        return {
            'nombre': nombre,
            'username': user.username,
            'email': perfil.email if perfil else '',
            'clases': clases,
        }
    except Exception as e:
        logger.warning(f"[IA-ctx] docente_propio: {e}")
        return {'nombre': user.username, 'username': user.username, 'clases': []}


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTRUCCIÓN DEL PROMPT — Diferenciado por rol
# ═══════════════════════════════════════════════════════════════════════════════

def _fmt(lst, empty='Ninguno ✅'):
    """Formatea una lista como viñetas para el prompt."""
    if not lst:
        return f'  {empty}'
    return '\n'.join(f'  • {item}' for item in lst[:MAX_ITEMS])


def _build_system_prompt(user) -> str:
    rol = getattr(user, 'rol', 'DESCONOCIDO')
    username = getattr(user, 'username', 'Sistema')
    cache_key = f"ia_system_prompt_{rol}_{username}"
    cached_prompt = cache.get(cache_key)
    if cached_prompt:
        return cached_prompt
    
    prompt = _build_system_prompt_raw(user)
    cache.set(cache_key, prompt, 60)
    return prompt

def _build_system_prompt_raw(user) -> str:
    rol      = getattr(user, 'rol', 'DESCONOCIDO')
    username = getattr(user, 'username', 'Sistema')
    ano      = date.today().year

    # ── DOCENTE: ve solo sus propios datos ────────────────────────────────────
    if rol == 'DOCENTE':
        d = _ctx_docente_propio(user)
        clases_txt = _fmt(d.get('clases', []), 'Sin clases asignadas. Contacta al administrador.')
        return f"""Eres el Asistente del Portal Docente — U.E.N. Colegio Apacuana. Año: {ano}.

DOCENTE AUTENTICADO: {d['nombre']} (@{username})
Email: {d.get('email') or 'No registrado'} | Clases: {len(d.get('clases', []))}

MIS CLASES ASIGNADAS:
{clases_txt}

REGLAS ESTRICTAS:
- SÉ EXTREMADAMENTE DIRECTO Y AL GRANO. Responde inmediatamente sin saludos (ej. "Hola", "Claro") ni rodeos.
- Responde únicamente a lo que se te pregunta sin sobreabundar en información adicional no solicitada.
- Si el usuario solo saluda (ej. "hola", "buenos días", etc.) o no hace una pregunta clara, salúdalo amablemente, identifícate como Tamarindo y pregúntale brevemente en qué puedes ayudarle.
- Solo puedes proporcionar información sobre este docente y sus clases.
- No reveles datos de otros docentes, datos financieros ni información sensible de otros.
- No elimines registros. Si algo falta, indica al docente que contacte al administrador.
- Si preguntan algo fuera de tu alcance, dilo claramente y sugiere a quién acudir.

TONO: Directo, ultra-conciso, sin adornos. Usa los datos reales del contexto. No inventes nada."""

    # ── ADMINISTRATIVO / PERSONAL: acceso completo ────────────────────────────
    exp  = _ctx_expedientes()
    doc  = _ctx_docentes()
    cal  = _ctx_calificaciones()
    hor  = _ctx_horarios()
    usr  = _ctx_usuarios()
    asist = _ctx_asistencias()

    dist_txt = ', '.join(f"{l}: {n}" for l, n in exp.get('distribucion', {}).items()) or 'N/D'

    # Docentes: formato detallado
    docentes_txt = '\n'.join(
        f"  • {d['nombre']} (@{d['username']}) — {'Activo' if d['activo'] else '🔴 Bloqueado'} — "
        f"Clases: {', '.join(d['asignaciones']) or 'SIN ASIGNACIÓN'} — "
        f"Notas: {d['notas_confirmadas']} conf. / {d['notas_borrador']} borrador"
        for d in doc.get('lista', [])
    ) or '  Sin docentes registrados.'

    return f"""Eres el Asistente Administrativo IA — U.E.N. Colegio Apacuana. Año: {ano}.
Usuario: {username} | Rol: {rol}

══════════════════════════════════════════════════════
  DATOS EN TIEMPO REAL — SNAPSHOT COMPLETO DEL SISTEMA
══════════════════════════════════════════════════════

📁 ESTUDIANTES Y EXPEDIENTES
• Total: {exp.get('total','N/D')} | Solventes: {exp.get('solventes','N/D')} | Incompletos: {exp.get('incompletos_count','N/D')}
• Distribución por año: {dist_txt}
• Observaciones conductuales: {exp.get('total_observaciones','N/D')}

Estudiantes SIN expediente ({len(exp.get('sin_expediente',[]))}):
{_fmt(exp.get('sin_expediente',[]), 'Todos tienen expediente ✅')}

Expedientes INCOMPLETOS:
{_fmt(exp.get('incompletos_lista',[]), 'Ninguno incompleto ✅')}

👨‍🏫 DOCENTES ({doc.get('total', 0)} registrados)
{docentes_txt}

Docentes SIN asignación activa:
{_fmt(doc.get('sin_asignacion', []), 'Todos tienen asignación ✅')}

Docentes con notas en BORRADOR (pendientes de confirmar):
{_fmt(doc.get('con_notas_borrador', []), 'Ninguno ✅')}

Docentes con CÉDULA FALTANTE:
{_fmt(doc.get('sin_cedula', []), 'Todos tienen cédula ✅')}

📊 CALIFICACIONES
• Período activo: {cal.get('periodo_activo','N/D')} | Total períodos: {cal.get('total_periodos','N/D')}
• Inscripciones: {cal.get('total_inscripciones','N/D')} | Asignaturas: {cal.get('total_asignaturas','N/D')}
• Asignaturas: {', '.join(cal.get('asignaturas',[])[:15])}
• Notas: L1={cal.get('notas_L1',0)} | L2={cal.get('notas_L2',0)} | L3={cal.get('notas_L3',0)} | DEF={cal.get('notas_DEF',0)}

📅 HORARIOS Y CLASES DETALLADOS
• Horarios: {hor.get('total_horarios','N/D')} | Bloques de clase: {hor.get('bloques_clase','N/D')} | Aulas: {hor.get('total_aulas','N/D')}

Horarios Detallados por Sección:
{_fmt(hor.get('por_seccion',[]), 'Sin horarios registrados')}

Horarios Detallados por Docente:
{_fmt(hor.get('detallados',[]), 'Sin horarios registrados')}

Conflictos de horario detectados:
{_fmt(hor.get('conflictos',[]), 'Sin conflictos ✅')}

📝 ASISTENCIA DEL PERSONAL (Últimos 15 días)
{_fmt(asist.get('resumen',[]), 'Sin registros')}

👥 USUARIOS DEL SISTEMA ({usr.get('total','N/D')} total)
• Administrativos: {', '.join(usr.get('administrativos', ['Ninguno']))}
• Personal: {', '.join(usr.get('personal', ['Ninguno']))}
• Bloqueados/Inactivos: {_fmt(usr.get('inactivos',[]), 'Ninguno ✅')}

══════════════════════════════════════════════════════
REGLAS DE OPERACIÓN:
1. SÉ EXTREMADAMENTE DIRECTO Y AL GRANO. Omite introducciones corteses, saludos (como "Hola", "Claro") o adornos. Da la respuesta de inmediato.
2. No sobreabundes en información. Responde exactamente lo que el usuario pide de forma ultra-concisa, sin explicaciones adicionales no solicitadas.
3. SIEMPRE usa los datos reales del contexto para responder. Nunca digas "no tengo acceso" si el dato está arriba.
4. Para responder "¿Cuántos...?" o "¿Quién...?": usa los nombres exactos del contexto, no respondas solo con números.
5. Si detectas un problema (duplicado, sin asignación, incompleto), menciónalo con el nombre exacto de la persona.
6. Nunca elimines datos. Si te piden borrar, sugiere inactivar o corregir y explica cómo.
7. Para cambios importantes, guía al usuario a la pantalla correcta del sistema.
8. Si el dato no está en el contexto, dilo claramente y sugiere dónde buscarlo.
9. Cruza información entre módulos cuando sea útil.
10. Si el usuario solo saluda (ej. "hola", "buenos días", etc.) o no hace una pregunta, salúdalo amablemente, preséntate como Tamarindo (el Asistente Administrativo IA) y pregúntale brevemente en qué puedes colaborar.

TONO: Ultra-directo, conciso, clínico. Usa emojis con moderación: 📋 ✅ ⚠️ 💡
Responde siempre en español. No inventes información."""


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINT PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def asistente_chat_view(request):
    """
    Endpoint del chat IA con contexto rico y acceso por roles.
    Body JSON: { "mensaje": "...", "historial": [...] }
    """
    try:
        data      = json.loads(request.body)
        mensaje   = str(data.get('mensaje', '')).strip()
        historial = data.get('historial', [])
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'error': 'Formato de solicitud inválido.'}, status=400)

    if not mensaje:
        return JsonResponse({'error': 'Mensaje vacío.'}, status=400)

    if len(mensaje) > 2000:
        return JsonResponse({'error': 'Mensaje demasiado largo (máx. 2000 caracteres).'}, status=400)

    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=GEMINI_API_KEY)

        # Historial de conversación (últimos turnos válidos)
        contents = []
        # Filtrar historial válido
        valid_history = [
            e for e in historial[-10:] 
            if e.get('role') in ('user', 'model') and e.get('text')
        ]
        
        # Asegurar que el primer turno sea 'user'
        while valid_history and valid_history[0].get('role') != 'user':
            valid_history.pop(0)

        # Construir contents asegurando alternancia
        last_role = None
        for entry in valid_history:
            role = entry.get('role')
            text = entry.get('text')
            
            # Si el rol es el mismo que el anterior, concatenamos el texto al último content
            if role == last_role and contents:
                contents[-1].parts.append(genai_types.Part(text="\n" + text))
            else:
                contents.append(
                    genai_types.Content(
                        role=role,
                        parts=[genai_types.Part(text=text)]
                    )
                )
                last_role = role

        if last_role == 'user' and contents:
            contents[-1].parts.append(genai_types.Part(text="\n" + mensaje))
        else:
            contents.append(
                genai_types.Content(
                    role='user',
                    parts=[genai_types.Part(text=mensaje)]
                )
            )

        system_prompt = _build_system_prompt(request.user)
        logger.info(f"[AsistenteIA] System prompt length: {len(system_prompt)} chars")

        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.25,
                    max_output_tokens=4096,
                ),
            )
        except Exception as api_err:
            logger.error(f"[AsistenteIA] Gemini API call failed: {api_err}", exc_info=True)
            return JsonResponse({
                'respuesta': f'⚠️ Error al consultar la IA: {str(api_err)[:200]}'
            })

        respuesta = getattr(response, 'text', None) or '⚠️ La IA no generó respuesta.'
        return JsonResponse({'respuesta': respuesta})

    except ImportError:
        return JsonResponse({
            'error': 'El paquete google-genai no está instalado. Ejecuta: pip install google-genai'
        }, status=500)
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[AsistenteIA] Error Gemini API: {error_msg}", exc_info=True)

        if '429' in error_msg or 'RESOURCE_EXHAUSTED' in error_msg:
            return JsonResponse({
                'respuesta': '⚠️ El límite de consultas de la IA se ha agotado temporalmente. Espera un momento e intenta de nuevo.'
            })
        elif '401' in error_msg or 'API_KEY_INVALID' in error_msg:
            return JsonResponse({
                'respuesta': '⚠️ La clave de API de Gemini no es válida. Contacta al administrador del sistema.'
            })

        return JsonResponse({
            'respuesta': '⚠️ El servicio de asistencia tuvo un problema técnico. Por favor, intenta de nuevo en unos instantes.'
        })

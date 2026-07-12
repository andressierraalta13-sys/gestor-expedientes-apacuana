"""
API de Auditoría — Endpoints para el Dashboard y Sistema de Aprobaciones
"""

import json
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now

from .models import EventoAuditoria, NotificacionOperativa, SolicitudAprobacion, Notificacion
from .ejecutor_solicitudes import ejecutar_accion_aprobada


# ─── Notificaciones Operativas (campana) ──────────────────────────────────────

@login_required
@require_GET
def api_eventos_recientes(request):
    from django.db.models import Q
    eventos_aud = NotificacionOperativa.objects.all().order_by('-fecha_creacion')[:20]
    
    eventos_dev = Notificacion.objects.filter(
        Q(usuario_destino=request.user) | Q(usuario_destino__isnull=True)
    ).order_by('-creado_en')[:20]
    
    combinados = []
    for e in eventos_aud:
        combinados.append({
            'id': e.id,
            'origen': 'AUDITORIA',
            'titulo': e.titulo,
            'mensaje': e.mensaje,
            'nivel_riesgo': e.nivel_riesgo,
            'modulo': e.modulo,
            'leido': e.leido,
            'conteo_agrupacion': e.conteo_agrupacion,
            'timestamp': e.fecha_creacion.strftime('%d/%m/%Y %I:%M %p'),
            'ts_raw': e.fecha_creacion.timestamp(),
        })
        
    for e in eventos_dev:
        combinados.append({
            'id': e.id,
            'origen': 'SISTEMA',
            'titulo': e.titulo,
            'mensaje': e.mensaje,
            'nivel_riesgo': 'INFORMATIVO' if e.tipo == 'ACTUALIZACION' else 'ADVERTENCIA',
            'modulo': 'SISTEMA',
            'leido': e.leido,
            'conteo_agrupacion': 1,
            'timestamp': e.creado_en.strftime('%d/%m/%Y %I:%M %p'),
            'ts_raw': e.creado_en.timestamp(),
        })
        
    combinados.sort(key=lambda x: x['ts_raw'], reverse=True)
    return JsonResponse({'eventos': combinados[:20]})


@login_required
@require_GET
def api_conteo_no_leidos(request):
    from django.db.models import Q
    total_aud = NotificacionOperativa.objects.filter(leido=False).count()
    criticos = NotificacionOperativa.objects.filter(leido=False, nivel_riesgo='CRITICO').count()
    medios   = NotificacionOperativa.objects.filter(leido=False, nivel_riesgo='ADVERTENCIA').count()
    
    total_dev = Notificacion.objects.filter(
        Q(usuario_destino=request.user) | Q(usuario_destino__isnull=True),
        leido=False
    ).count()
    
    return JsonResponse({'total': total_aud + total_dev, 'criticos': criticos, 'medios': medios})


@login_required
@csrf_exempt
def api_marcar_leido(request, evento_id):
    if request.method not in ('POST', 'PATCH'):
        return JsonResponse({'error': 'Método no permitido.'}, status=405)
    origen = request.GET.get('origen', 'AUDITORIA')
    try:
        if origen == 'SISTEMA':
            evento = Notificacion.objects.get(id=evento_id)
            evento.leido = True
            evento.save(update_fields=['leido'])
        else:
            evento = NotificacionOperativa.objects.get(id=evento_id)
            evento.leido = True
            evento.conteo_agrupacion = 1
            evento.save(update_fields=['leido', 'conteo_agrupacion'])
        return JsonResponse({'ok': True, 'id': evento_id})
    except (NotificacionOperativa.DoesNotExist, Notificacion.DoesNotExist):
        return JsonResponse({'error': 'Notificación no encontrada.'}, status=404)


@login_required
@csrf_exempt
def api_marcar_todos_leidos(request):
    if request.method not in ('POST', 'PATCH'):
        return JsonResponse({'error': 'Método no permitido.'}, status=405)
    from django.db.models import Q
    count1 = NotificacionOperativa.objects.filter(leido=False).update(leido=True, conteo_agrupacion=1)
    count2 = Notificacion.objects.filter(
        Q(usuario_destino=request.user) | Q(usuario_destino__isnull=True),
        leido=False
    ).update(leido=True)
    return JsonResponse({'ok': True, 'marcados': count1 + count2})


@login_required
@csrf_exempt
def api_eliminar_notificacion(request, evento_id):
    if request.method not in ('POST', 'DELETE'):
        return JsonResponse({'error': 'Método no permitido.'}, status=405)
    origen = request.GET.get('origen', 'AUDITORIA')
    try:
        if origen == 'SISTEMA':
            notif = Notificacion.objects.get(id=evento_id)
        else:
            notif = NotificacionOperativa.objects.get(id=evento_id)
        notif.delete()
        return JsonResponse({'ok': True, 'id': evento_id})
    except (NotificacionOperativa.DoesNotExist, Notificacion.DoesNotExist):
        return JsonResponse({'error': 'Notificación no encontrada.'}, status=404)


@login_required
@csrf_exempt
def api_vaciar_notificaciones(request):
    if request.method not in ('POST', 'DELETE'):
        return JsonResponse({'error': 'Método no permitido.'}, status=405)
    count, _ = NotificacionOperativa.objects.all().delete()
    return JsonResponse({'ok': True, 'eliminadas': count})


# ═══════════════════════════════════════════════════════════════════════════════
# SISTEMA DE APROBACIONES — APIs
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@csrf_exempt
def api_crear_solicitud(request):
    """Personal crea una solicitud de aprobación para una acción crítica."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido.'}, status=405)
    if request.user.rol != 'PERSONAL':
        return JsonResponse({'error': 'Solo el rol Personal puede crear solicitudes.'}, status=403)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido.'}, status=400)

    accion = data.get('accion', 'otra_accion')
    modulo = str(data.get('modulo', '')).strip()
    descripcion = str(data.get('descripcion', '')).strip()
    payload_json = data.get('payload', None)

    if not descripcion or not modulo:
        return JsonResponse({'error': 'Módulo y descripción son obligatorios.'}, status=400)

    # Evitar duplicados pendientes del mismo tipo
    if SolicitudAprobacion.objects.filter(solicitante=request.user, accion=accion, estado='PENDIENTE').exists():
        return JsonResponse({
            'error': 'Ya tienes una solicitud pendiente de este tipo. Espera a que sea procesada.'
        }, status=400)

    solicitud = SolicitudAprobacion.objects.create(
        solicitante=request.user, accion=accion, modulo=modulo,
        descripcion=descripcion, payload_json=payload_json,
    )

    from .models import registrar_evento, lanzar_alerta_operativa
    registrar_evento(
        tipo='SOLICITUD_CONTROLADA',
        descripcion=f'{request.user.username} solicitó: {descripcion}',
        modulo=modulo, usuario=request.user.username,
        nivel_riesgo='INFORMATIVO', exitoso=True,
        impacto='Acción retenida. Pendiente de aprobación administrativa.',
        detalle_json={'solicitud_id': solicitud.id, 'accion': accion}
    )
    lanzar_alerta_operativa(
        titulo=f'Nueva solicitud de {request.user.username}',
        mensaje=f'{request.user.username} solicita: {descripcion} (Módulo: {modulo})',
        nivel_riesgo='ADVERTENCIA', modulo='Aprobaciones',
        agrupacion_hash=f'solicitud-nueva-{request.user.id}-{accion}'
    )
    return JsonResponse({
        'ok': True, 'solicitud_id': solicitud.id,
        'mensaje': 'Solicitud enviada al Administrativo. Recibirás una notificación cuando sea procesada.',
        'expira_en': solicitud.fecha_expiracion.strftime('%d/%m/%Y %I:%M %p'),
    })


@login_required
@require_GET
def api_solicitudes_pendientes(request):
    if request.user.rol not in ['ADMINISTRATIVO', 'DESARROLLADOR']:
        return JsonResponse({'error': 'No autorizado.'}, status=403)
    _marcar_expiradas()
    qs = SolicitudAprobacion.objects.filter(estado='PENDIENTE').select_related('solicitante')
    return JsonResponse({'solicitudes': [_serializar(s) for s in qs], 'total': qs.count()})


@login_required
@require_GET
def api_historial_solicitudes(request):
    if request.user.rol not in ['ADMINISTRATIVO', 'DESARROLLADOR']:
        return JsonResponse({'error': 'No autorizado.'}, status=403)
    _marcar_expiradas()
    estado = request.GET.get('estado', '')
    qs = SolicitudAprobacion.objects.select_related('solicitante', 'procesado_por')
    if estado:
        qs = qs.filter(estado=estado)
    qs = qs[:50]
    return JsonResponse({'solicitudes': [_serializar(s) for s in qs], 'total': qs.count()})


@login_required
@csrf_exempt
def api_aprobar_solicitud(request, solicitud_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido.'}, status=405)
    if request.user.rol not in ['ADMINISTRATIVO', 'DESARROLLADOR']:
        return JsonResponse({'error': 'No autorizado.'}, status=403)
    try:
        solicitud = SolicitudAprobacion.objects.get(id=solicitud_id)
    except SolicitudAprobacion.DoesNotExist:
        return JsonResponse({'error': 'Solicitud no encontrada.'}, status=404)
    if solicitud.estado != 'PENDIENTE':
        return JsonResponse({'error': f'La solicitud ya fue procesada ({solicitud.get_estado_display()}).'}, status=400)
    if solicitud.esta_expirada:
        solicitud.estado = 'EXPIRADA'
        solicitud.save(update_fields=['estado'])
        return JsonResponse({'error': 'La solicitud ha expirado.'}, status=400)

    try:
        data = json.loads(request.body)
        comentario = str(data.get('comentario', '')).strip()[:1000]
    except Exception:
        comentario = ''

    resultado = ejecutar_accion_aprobada(solicitud)
    if resultado['ok']:
        solicitud.estado = 'APROBADA'
        solicitud.procesado_por = request.user
        solicitud.comentario_admin = comentario
        solicitud.fecha_respuesta = now()
        solicitud.save()
        from .models import registrar_evento
        registrar_evento(
            tipo='SOLICITUD_APROBADA',
            descripcion=f'{request.user.username} aprobó: {solicitud.descripcion}',
            modulo=solicitud.modulo, usuario=request.user.username,
            nivel_riesgo='INFORMATIVO', exitoso=True,
            detalle_json={'solicitud_id': solicitud.id}
        )
        return JsonResponse({'ok': True, 'mensaje': f'Aprobada y ejecutada. {resultado["mensaje"]}'})
    return JsonResponse({'error': f'Error al ejecutar: {resultado["mensaje"]}'}, status=500)


@login_required
@csrf_exempt
def api_rechazar_solicitud(request, solicitud_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido.'}, status=405)
    if request.user.rol not in ['ADMINISTRATIVO', 'DESARROLLADOR']:
        return JsonResponse({'error': 'No autorizado.'}, status=403)
    try:
        solicitud = SolicitudAprobacion.objects.get(id=solicitud_id)
    except SolicitudAprobacion.DoesNotExist:
        return JsonResponse({'error': 'Solicitud no encontrada.'}, status=404)
    if solicitud.estado != 'PENDIENTE':
        return JsonResponse({'error': f'La solicitud ya fue procesada.'}, status=400)

    try:
        data = json.loads(request.body)
        comentario = str(data.get('comentario', '')).strip()[:1000]
    except Exception:
        comentario = ''

    solicitud.estado = 'RECHAZADA'
    solicitud.procesado_por = request.user
    solicitud.comentario_admin = comentario
    solicitud.fecha_respuesta = now()
    solicitud.save()
    from .models import registrar_evento
    registrar_evento(
        tipo='SOLICITUD_RECHAZADA',
        descripcion=f'{request.user.username} rechazó: {solicitud.descripcion}',
        modulo=solicitud.modulo, usuario=request.user.username,
        nivel_riesgo='INFORMATIVO', exitoso=True,
        detalle_json={'solicitud_id': solicitud.id}
    )
    return JsonResponse({'ok': True, 'mensaje': 'Solicitud rechazada.'})


@login_required
@require_GET
def api_mis_solicitudes(request):
    if request.user.rol != 'PERSONAL':
        return JsonResponse({'error': 'No autorizado.'}, status=403)
    _marcar_expiradas()
    qs = SolicitudAprobacion.objects.filter(solicitante=request.user).select_related('procesado_por')[:30]
    return JsonResponse({'solicitudes': [_serializar(s) for s in qs], 'total': qs.count()})


@login_required
@require_GET
def api_conteo_solicitudes(request):
    _marcar_expiradas()
    if request.user.rol in ['ADMINISTRATIVO', 'DESARROLLADOR']:
        total = SolicitudAprobacion.objects.filter(estado='PENDIENTE').count()
    elif request.user.rol == 'PERSONAL':
        total = SolicitudAprobacion.objects.filter(
            solicitante=request.user, estado__in=['APROBADA', 'RECHAZADA'], leida_por_personal=False
        ).count()
    else:
        total = 0
    return JsonResponse({'total': total, 'rol': request.user.rol})


@login_required
@csrf_exempt
def api_marcar_solicitud_leida(request, solicitud_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido.'}, status=405)
    if request.user.rol != 'PERSONAL':
        return JsonResponse({'error': 'No autorizado.'}, status=403)
    try:
        s = SolicitudAprobacion.objects.get(id=solicitud_id, solicitante=request.user)
        s.leida_por_personal = True
        s.save(update_fields=['leida_por_personal'])
        return JsonResponse({'ok': True})
    except SolicitudAprobacion.DoesNotExist:
        return JsonResponse({'error': 'Solicitud no encontrada.'}, status=404)


# ── Vistas de Página ──────────────────────────────────────────────────────────

@login_required
def aprobaciones_view(request):
    if request.user.rol not in ['ADMINISTRATIVO', 'DESARROLLADOR']:
        from django.shortcuts import render
        return render(request, '403.html', {'mensaje': 'No tienes permisos para ver esta sección.'}, status=403)
    _marcar_expiradas()
    pendientes = SolicitudAprobacion.objects.filter(estado='PENDIENTE').select_related('solicitante')
    historial = SolicitudAprobacion.objects.filter(
        estado__in=['APROBADA', 'RECHAZADA', 'EXPIRADA']
    ).select_related('solicitante', 'procesado_por')[:30]
    from django.shortcuts import render
    return render(request, 'auditoria/aprobaciones.html', {
        'pendientes': pendientes,
        'historial': historial,
        'total_pendientes': pendientes.count(),
    })


@login_required
def notificaciones_personal_view(request):
    if request.user.rol != 'PERSONAL':
        from django.shortcuts import redirect
        return redirect('home')
    _marcar_expiradas()
    solicitudes = SolicitudAprobacion.objects.filter(
        solicitante=request.user
    ).select_related('procesado_por')
    from django.shortcuts import render
    return render(request, 'auditoria/notificaciones_personal.html', {
        'solicitudes': solicitudes,
        'no_leidas': solicitudes.filter(estado__in=['APROBADA', 'RECHAZADA'], leida_por_personal=False).count(),
    })


# ── Utilidades internas ───────────────────────────────────────────────────────

def _marcar_expiradas():
    SolicitudAprobacion.objects.filter(estado='PENDIENTE', fecha_expiracion__lt=now()).update(estado='EXPIRADA')


def _serializar(s: SolicitudAprobacion) -> dict:
    return {
        'id': s.id,
        'accion': s.accion,
        'accion_display': s.get_accion_display(),
        'modulo': s.modulo,
        'descripcion': s.descripcion,
        'estado': s.estado,
        'estado_display': s.get_estado_display(),
        'solicitante': s.solicitante.username,
        'solicitante_nombre': s.solicitante.nombre_completo or s.solicitante.username,
        'procesado_por': s.procesado_por.username if s.procesado_por else None,
        'comentario_admin': s.comentario_admin,
        'leida_por_personal': s.leida_por_personal,
        'fecha_solicitud': s.fecha_solicitud.strftime('%d/%m/%Y %I:%M %p'),
        'fecha_expiracion': s.fecha_expiracion.strftime('%d/%m/%Y %I:%M %p'),
        'fecha_respuesta': s.fecha_respuesta.strftime('%d/%m/%Y %I:%M %p') if s.fecha_respuesta else None,
        'tiempo_restante': s.tiempo_restante_display,
        'esta_expirada': s.esta_expirada,
    }


@login_required
def centro_notificaciones_view(request):
    """
    Renderiza el Centro de Notificaciones unificado.
    Muestra notificaciones de auditoría y notificaciones globales (sistema/actualización).
    """
    from django.db.models import Q
    from django.shortcuts import render

    # Traer notificaciones globales y las asignadas a este usuario
    notificaciones = Notificacion.objects.filter(
        Q(usuario_destino=request.user) | Q(usuario_destino__isnull=True)
    ).order_by('-creado_en')[:50]

    return render(request, 'notificaciones/centro.html', {'notificaciones': notificaciones})

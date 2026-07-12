from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from .models import RegistroAsistencia
from usuarios.models import Usuario
from estudiantes.models import Estudiante
import json

@login_required
def asistencias_personal_view(request):
    fecha_hoy = timezone.localdate()
    # Precargar asistencias de hoy y filtrar solo personal activo
    personal = Usuario.objects.exclude(rol='DESARROLLADOR').filter(is_active=True).order_by('nombre_completo')
    # Precargar asistencias de hoy
    asistencias = RegistroAsistencia.objects.filter(tipo='PERSONAL', fecha=fecha_hoy)
    asistencias_dict = {a.personal_id: a.asistio for a in asistencias}
    
    lista = []
    presentes = 0
    for p in personal:
        asistio = asistencias_dict.get(p.id, False)
        if asistio: presentes += 1
        lista.append({
            'id': p.id,
            'nombre': p.nombre_completo or p.username,
            'rol': p.rol,
            'asistio': asistio
        })
        
    context = {
        'lista': lista,
        'fecha': fecha_hoy,
        'total': len(lista),
        'presentes': presentes,
        'ausentes': len(lista) - presentes
    }
    return render(request, 'asistencias/personal.html', context)


@login_required
def registro_historico_view(request):
    registros = RegistroAsistencia.objects.values('fecha').distinct().order_by('-fecha')
    return render(request, 'asistencias/registro.html', {'registros': registros})

@login_required
def detalle_registro_view(request, fecha):
    asistencias = RegistroAsistencia.objects.filter(fecha=fecha)
    
    from docentes.models import RegistroAsistencia as DocenteAsistencia
    asistencias_docentes = DocenteAsistencia.objects.filter(fecha=fecha).select_related('asignatura', 'estudiante')
    
    from collections import defaultdict
    agrupadas = defaultdict(list)
    for a in asistencias_docentes:
        ano = a.asignatura.ano_grado if a.asignatura else ''
        seccion = a.seccion
        asig_nombre = a.asignatura.nombre if a.asignatura else ''
        key = (ano, seccion, asig_nombre)
        agrupadas[key].append(a)
    
    grupos_ordenados = []
    for key in sorted(agrupadas.keys()):
        asistencias_grupo = sorted(agrupadas[key], key=lambda x: x.estudiante.apellidos if x.estudiante else '')
        
        asistidos = sum(1 for a in asistencias_grupo if a.estado == 'PRESENTE')
        ausentes = sum(1 for a in asistencias_grupo if a.estado == 'AUSENTE')
        retrasos = sum(1 for a in asistencias_grupo if a.estado == 'RETARDO')
        justificados = sum(1 for a in asistencias_grupo if a.estado == 'JUSTIFICADO')
        
        docente = 'Desconocido'
        if asistencias_grupo and asistencias_grupo[0].registrado_por:
            reg_por = asistencias_grupo[0].registrado_por
            docente = getattr(reg_por, 'nombre_completo', None) or reg_por.username

        grupos_ordenados.append({
            'ano': key[0],
            'seccion': key[1],
            'asignatura': key[2],
            'asistencias': asistencias_grupo,
            'asistidos': asistidos,
            'ausentes': ausentes,
            'retrasos': retrasos,
            'justificados': justificados,
            'docente': docente
        })

    context = {
        'fecha': fecha,
        'asistencias': asistencias,
        'grupos_docentes': grupos_ordenados
    }
    return render(request, 'asistencias/detalle_registro.html', context)

@login_required
def api_marcar_asistencia(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        tipo = data.get('tipo')
        asistio = data.get('asistio')
        fecha = timezone.localdate()
        
        if tipo == 'PERSONAL':
            personal_id = data.get('id')
            reg, created = RegistroAsistencia.objects.update_or_create(
                tipo=tipo, fecha=fecha, personal_id=personal_id,
                defaults={'asistio': asistio, 'registrado_por': request.user}
            )
        elif tipo == 'ESTUDIANTE':
            cedula = data.get('cedula')
            nombre = data.get('nombre')
            reg, created = RegistroAsistencia.objects.update_or_create(
                tipo=tipo, fecha=fecha, estudiante_cedula=cedula,
                defaults={'estudiante_nombre': nombre, 'asistio': asistio, 'registrado_por': request.user}
            )
            
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'}, status=400)

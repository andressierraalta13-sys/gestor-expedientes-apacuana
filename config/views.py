import logging
from io import BytesIO
from PIL import Image
from django.shortcuts import render, redirect, get_object_or_404
from django.core.mail import send_mail
from urllib.parse import quote
from django.http import JsonResponse
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from estudiantes.models import Expediente, Estudiante, ObservacionConductual
from graduacion.models import TituloBachiller
from calificaciones.models import Calificacion

logger = logging.getLogger(__name__)



@login_required
def dashboard_view(request):
    from auditoria.models import EventoAuditoria
    
    solventes = Expediente.objects.filter(estatus='SOLVENTE').count()
    incompletos = Expediente.objects.filter(estatus='INCOMPLETO').count()
    titulos = TituloBachiller.objects.count()

    logs_normalized = []
    
    # Obtener los últimos eventos de auditoría transversales
    eventos = EventoAuditoria.objects.all().order_by('-timestamp')[:10]
    
    for evento in eventos:
        color = 'var(--primary)'
        icono = 'information-circle-outline'
        
        if evento.nivel_riesgo == 'CRITICO':
            color = 'var(--error)'
            icono = 'warning-outline'
        elif evento.nivel_riesgo == 'MEDIO':
            color = 'var(--secondary)'
            icono = 'alert-circle-outline'
            
        logs_normalized.append({
            'icono': icono,
            'color': color,
            'titulo': f"[{evento.modulo}] {evento.usuario}",
            'detalle': evento.descripcion,
            'fecha': evento.timestamp
        })
    
    context = {
        'solventes': solventes,
        'incompletos': incompletos,
        'titulos': titulos,
        'audit_logs': logs_normalized
    }
    return render(request, 'dashboards/home.html', context)

def aplicar_filtro_busqueda(queryset, query):
    import re
    from django.db.models import Q
    
    query = query.strip()
    if not query:
        return queryset
        
    clean_digits = re.sub(r'\D', '', query)
    words = [w for w in query.split() if not re.match(r'^(?:[VEPvep][-.]?)?\d+[-.\d]*$', w)]
    
    q_filter = Q()
    if words:
        name_q = Q()
        for word in words:
            name_q &= (Q(estudiante__nombres__icontains=word) | Q(estudiante__apellidos__icontains=word))
        q_filter = name_q
        
    if clean_digits:
        if q_filter:
            q_filter &= Q(estudiante__cedula_identidad__icontains=clean_digits)
        else:
            q_filter = Q(estudiante__cedula_identidad__icontains=clean_digits)
            
    return queryset.filter(q_filter)

@login_required
def expedientes_view(request):
    try:
        query = request.GET.get('q', '').strip()
        # Filtrar expedientes huérfanos
        expedientes = Expediente.objects.filter(estudiante__isnull=False).select_related('estudiante')
        
        if query:
            expedientes = aplicar_filtro_busqueda(expedientes, query)
        
        # Pre-agrupar por año y sección para el filtro "Filtrar por Año"
        # (dictsort con propiedades anidadas no funciona correctamente en Django templates)
        from collections import OrderedDict
        agrupados = OrderedDict()
        for exp in expedientes.order_by('estudiante__ano_cursando', 'estudiante__seccion'):
            ano_display = exp.estudiante.get_ano_cursando_display()
            seccion = exp.estudiante.seccion or 'Única'
            if ano_display not in agrupados:
                agrupados[ano_display] = OrderedDict()
            if seccion not in agrupados[ano_display]:
                agrupados[ano_display][seccion] = []
            agrupados[ano_display][seccion].append(exp)
        
        # Convertir a estructura que el template pueda iterar
        expedientes_agrupados = []
        for ano_display, secciones in agrupados.items():
            secciones_list = [{'seccion': sec, 'expedientes': exps} for sec, exps in secciones.items()]
            expedientes_agrupados.append({'ano': ano_display, 'secciones': secciones_list})
            
        return render(request, 'expedientes/lista_expedientes.html', {
            'expedientes': expedientes,
            'expedientes_agrupados': expedientes_agrupados,
        })
    except Exception as e:
        import traceback
        error_msg = f"Error 500 en expedientes_view: {str(e)}\n\n{traceback.format_exc()}"
        from django.http import HttpResponse
        return HttpResponse(f"<pre>{error_msg}</pre>", status=500)

@login_required
def lista_solventes_view(request):
    expedientes = Expediente.objects.filter(estudiante__isnull=False, estatus='SOLVENTE').select_related('estudiante')
    return render(request, 'expedientes/solventes.html', {'expedientes': expedientes})

@login_required
def lista_incompletos_view(request):
    expedientes = Expediente.objects.filter(estudiante__isnull=False, estatus='INCOMPLETO').select_related('estudiante')
    # Pre-calculate missing docs for each incomplete expediente
    for exp in expedientes:
        faltantes = []
        if not exp.copia_cedula: faltantes.append('Copia C.I.')
        if not exp.partida_nacimiento: faltantes.append('Partida de Nacimiento')
        if not exp.notas_certificadas_previas: faltantes.append('Notas Certificadas')
        if not exp.fotografias: faltantes.append('Fotografías')
        exp.faltantes_list = faltantes

    return render(request, 'expedientes/incompletos.html', {'expedientes': expedientes})


@login_required
def api_buscar_expedientes(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'resultados': []})
        
    expedientes = Expediente.objects.filter(estudiante__isnull=False).select_related('estudiante')
    expedientes = aplicar_filtro_busqueda(expedientes, query)[:6]
    
    data = []
    for exp in expedientes:
        data.append({
            'nombres': f"{exp.estudiante.nombres} {exp.estudiante.apellidos}",
            'cedula': exp.estudiante.cedula_identidad,
            'estatus': exp.get_estatus_display(),
            'url': f"/expedientes/?q={exp.estudiante.cedula_identidad}"
        })
    return JsonResponse({'resultados': data})

@login_required
def api_check_estudiante(request):
    cedula = request.GET.get('cedula', '').strip()
    if not cedula:
        return JsonResponse({'existe': False})
    
    estudiante = Estudiante.objects.filter(cedula_identidad=cedula).first()
    if estudiante:
        mapa_grados = {
            11: '1er Grado', 12: '2do Grado', 13: '3er Grado',
            14: '4to Grado', 15: '5to Grado', 16: '6to Grado',
            1: '1er Año', 2: '2do Año', 3: '3er Año', 
            4: '4to Año', 5: '5to Año', 6: 'Egresado/Graduado'
        }
        return JsonResponse({
            'existe': True,
            'ano_cursando': estudiante.ano_cursando,
            'ano_texto': mapa_grados.get(estudiante.ano_cursando, str(estudiante.ano_cursando))
        })
    return JsonResponse({'existe': False})

# carga_masiva_view fue migrada a calificaciones/views.py
# La URL /calificaciones/ ahora apunta al nuevo módulo de carga de alumnos
def _carga_masiva_view_legacy(request):
    from apps.calificaciones.excel_utils import pd
    import re
    from django.db import transaction
    from inscripciones.models import Asignatura, Inscripcion, PeriodoAcademico
    
    if request.method == 'POST' and request.FILES.get('archivo_excel'):
        excel_file = request.FILES['archivo_excel']
        filename = excel_file.name.upper()
        
        if not filename.endswith(('.XLSX', '.XLS')):
            return render(request, 'calificaciones/carga_masiva.html', {'error': 'Formato intruso detectado, suba solo .xlsx'})
            
        # Extracción de Inteligencia Regex Semántica (Ej: 22041426_1ER_AÑO.xlsx)
        cedula_match = re.search(r'(\d{7,9})', filename)
        
        # Mapeo ordinal venezolano: detectamos 1ER, 2DO, 3ER, 4TO, 5TO
        ano_patterns = {
            '1ER': 1, '2DO': 2, '3ER': 3, '4TO': 4, '5TO': 5,
            '1RO': 1, '2NDO': 2, '3RO': 3,  # Variantes alternativas
        }
        ano_grado = None
        for pattern, grado in ano_patterns.items():
            if pattern in filename:
                ano_grado = grado
                break
        
        if not cedula_match or ano_grado is None:
            return render(request, 'calificaciones/carga_masiva.html', {
                'error': f'Imposible extraer de "{excel_file.name}". Usa formato: Cedula_1ER_AÑO.xlsx (Ej: 22041426_1ER_AÑO.xlsx)'
            })

        cedula = cedula_match.group(1)
        nombres_ano = {1: '1er', 2: '2do', 3: '3er', 4: '4to', 5: '5to'}
        
        estudiante = Estudiante.objects.filter(cedula_identidad=cedula).first()
        if not estudiante:
            return render(request, 'calificaciones/carga_masiva.html', {'error': f'V-{cedula} inexistente en Base de Datos.'})
            
        try:
            # Lectura cruda sin encabezados (el Excel tiene multi-headers con celdas combinadas)
            df_raw = pd.read_excel(excel_file, header=None)
            
            # === FASE 1: ESCANEO ESTRUCTURAL DEL DOCUMENTO ===
            # Buscamos la fila que contiene "ASIGNATURAS" para anclar la posición
            asig_row_idx = None
            col_asig = None
            col_def = None
            col_l1 = None
            col_l2 = None
            col_l3 = None
            
            for idx in range(min(20, len(df_raw))):
                for ci, val in enumerate(df_raw.iloc[idx]):
                    vs = str(val).upper().strip()
                    if 'ASIGNATURA' in vs:
                        asig_row_idx = idx
                        col_asig = ci
                        break
                if asig_row_idx is not None:
                    break
            
            if asig_row_idx is None:
                return render(request, 'calificaciones/carga_masiva.html', {
                    'error': 'No se encontró la columna "ASIGNATURAS" en el documento Excel.'
                })
            
            # Escaneamos MÚLTIPLES filas para encontrar LAPSO y DEFINITIVA
            # En Excels con celdas combinadas multi-fila, los LAPSO pueden estar
            # en la MISMA fila que ASIGNATURAS o en la fila de ARRIBA
            rows_to_scan = [asig_row_idx]
            if asig_row_idx > 0:
                rows_to_scan.insert(0, asig_row_idx - 1)  # Fila superior primero
            if asig_row_idx > 1:
                rows_to_scan.insert(0, asig_row_idx - 2)  # Dos filas arriba también
            
            for scan_idx in rows_to_scan:
                scan_row = df_raw.iloc[scan_idx]
                for ci, val in enumerate(scan_row):
                    vs = str(val).upper().strip()
                    if ('DEFINITIVA' in vs or 'NOTA FINAL' in vs) and col_def is None:
                        col_def = ci
                    elif ('LAPSO III' in vs or 'LAPSO 3' in vs) and col_l3 is None:
                        col_l3 = ci
                    elif ('LAPSO II' in vs or 'LAPSO 2' in vs) and col_l2 is None:
                        col_l2 = ci
                    elif ('LAPSO I' in vs or 'LAPSO 1' in vs) and col_l1 is None:
                        col_l1 = ci
            
            # Detectar sub-encabezados (Califi / Inasis)
            sub_idx = asig_row_idx + 1
            has_sub = False
            if sub_idx < len(df_raw):
                sub_text = ' '.join([str(v).upper() for v in df_raw.iloc[sub_idx].values if str(v) != 'nan'])
                has_sub = 'CALIFI' in sub_text or 'INASIS' in sub_text
            
            data_start = (sub_idx + 1) if has_sub else (asig_row_idx + 1)
            
            # Verificación de integridad con diagnóstico
            missing = []
            if col_asig is None: missing.append('ASIGNATURAS')
            if col_l1 is None: missing.append('LAPSO I')
            if col_l2 is None: missing.append('LAPSO II')
            if col_l3 is None: missing.append('LAPSO III')
            if col_def is None: missing.append('DEFINITIVA')
            if missing:
                debug_rows = {}
                for si in rows_to_scan:
                    debug_rows[f'Fila {si}'] = [f'{ci}:{str(v)[:20]}' for ci, v in enumerate(df_raw.iloc[si]) if str(v) != 'nan']
                return render(request, 'calificaciones/carga_masiva.html', {
                    'error': f'No se localizaron: {", ".join(missing)}. Filas escaneadas: {debug_rows}'
                })
            
            # Guardar diagnóstico para el mensaje de éxito
            diag_cols = f'ASIG=col{col_asig}, L1=col{col_l1}, L2=col{col_l2}, L3=col{col_l3}, DEF=col{col_def}'
            first_data = df_raw.iloc[data_start] if data_start < len(df_raw) else None
            diag_sample = ''
            if first_data is not None:
                diag_sample = f' | Ejemplo fila {data_start}: L1={first_data.iloc[col_l1]}, L2={first_data.iloc[col_l2]}, L3={first_data.iloc[col_l3]}, DEF={first_data.iloc[col_def]}'
            
            # === FASE 2: PERSISTENCIA EN BASE DE DATOS ===
            periodo, _ = PeriodoAcademico.objects.get_or_create(activo=True, defaults={
                'nombre': 'PERIODO ACTUAL (PRED)', 'fecha_inicio': '2025-01-01', 'fecha_fin': '2028-12-30'
            })
            
            def safe_float(val):
                try:
                    f = float(val)
                    return f if f == f else None
                except (ValueError, TypeError):
                    return None
            
            with transaction.atomic():
                inscripcion, _ = Inscripcion.objects.get_or_create(
                    estudiante=estudiante,
                    periodo=periodo,
                    defaults={'ano_grado': ano_grado, 'seccion': 'U'}
                )
                
                # Limpieza automática: borrar calificaciones anteriores de este año
                # para permitir re-subidas limpias sin datos fantasma
                old_count = Calificacion.objects.filter(
                    inscripcion=inscripcion,
                    asignatura__ano_grado=ano_grado
                ).delete()[0]
                
                guardados = 0
                omitidos = 0
                for idx in range(data_start, len(df_raw)):
                    row = df_raw.iloc[idx]
                    materia_nombre = str(row.iloc[col_asig]).strip().upper()
                    
                    # Filtro IA: Saltar filas basura (vacías, promedios, pendientes, numéricas)
                    if (not materia_nombre
                        or materia_nombre == 'NAN'
                        or 'PROMEDIO' in materia_nombre
                        or 'PENDIENTE' in materia_nombre
                        or materia_nombre.replace(' ', '') == ''):
                        omitidos += 1
                        continue
                    
                    # Filtro anti-numérico: rechazar valores como "20", "19.75" que son promedios filtrados
                    try:
                        float(materia_nombre)
                        omitidos += 1
                        continue  # Es un número, no una materia
                    except ValueError:
                        pass
                    
                    asignatura, _ = Asignatura.objects.get_or_create(
                        nombre=materia_nombre,
                        ano_grado=ano_grado,
                        defaults={'codigo': f'A{ano_grado}-{materia_nombre[:3]}'}
                    )
                    
                    notas_map = {
                        'L1': safe_float(row.iloc[col_l1]),
                        'L2': safe_float(row.iloc[col_l2]),
                        'L3': safe_float(row.iloc[col_l3]),
                        'DEF': safe_float(row.iloc[col_def]),
                    }
                    
                    for tipo, val in notas_map.items():
                        if val is not None:
                            Calificacion.objects.update_or_create(
                                inscripcion=inscripcion,
                                asignatura=asignatura,
                                tipo=tipo,
                                defaults={'nota': val}
                            )
                            guardados += 1
            
            # Algoritmo de Excelencia y Promoción Automática
            from django.db.models import Avg
            promedio_def = Calificacion.objects.filter(inscripcion=inscripcion, tipo='DEF').aggregate(Avg('nota'))['nota__avg']
            msj_promocion = ""
            if promedio_def and promedio_def >= 18.0:
                if estudiante.ano_cursando <= ano_grado and estudiante.ano_cursando < 5:
                    nuevo_ano = estudiante.ano_cursando + 1
                    estudiante.ano_cursando = nuevo_ano
                    estudiante.save()
                    msj_promocion = f" ESTUDIANTE MOSTRÓ EXCELENCIA (Promedio: {promedio_def:.2f}) -> PROMOVIDO AUTOMÁTICAMENTE A {nuevo_ano}TO AÑO."
                elif estudiante.ano_cursando <= ano_grado and estudiante.ano_cursando == 5:
                    estudiante.ano_cursando = 6 # Egresado
                    estudiante.save()
                    msj_promocion = f" ESTUDIANTE MOSTRÓ EXCELENCIA (Promedio: {promedio_def:.2f}) -> PROMOVIDO A CONDICIÓN DE GRADUANDO."

            return render(request, 'calificaciones/carga_masiva.html', {
                'success': f'Algoritmo completado. Se inyectaron {guardados} calificaciones para V-{cedula} ({nombres_ano[ano_grado]} Año). {omitidos} filas omitidas.{msj_promocion}'
            })
            
        except Exception as e:
            return render(request, 'calificaciones/carga_masiva.html', {'error': f'Fallo crítico de motor Pandas: {str(e)}'})

    return render(request, 'calificaciones/carga_masiva.html')

@login_required
def titulos_view(request):
    elegibles = Expediente.objects.filter(estatus='SOLVENTE').select_related('estudiante')
    return render(request, 'graduacion/emision_titulos.html', {'elegibles': elegibles})

@login_required
def auditoria_view(request):
    logs_normalized = []
    from auditoria.models import EventoAuditoria
    
    for evento in EventoAuditoria.objects.all().order_by('-timestamp')[:500]:
        icono = 'information-circle-outline'
        if evento.modulo == 'Expedientes':
            icono = 'folder-open-outline'
        elif evento.modulo == 'Calificaciones':
            icono = 'document-text-outline'
        elif evento.modulo == 'Horarios':
            icono = 'calendar-outline'
        elif evento.modulo == 'Usuarios':
            icono = 'people-outline'

        accion_db = 'INFO'
        if evento.tipo == 'CREACION' or 'creado' in evento.descripcion.lower() or 'creó' in evento.descripcion.lower():
            accion_db = 'INSERT'
        elif evento.tipo in ['MODIFICACION', 'PAGO_INDIVIDUAL', 'PAGO_MASIVO_OK'] or 'modificad' in evento.descripcion.lower() or 'editad' in evento.descripcion.lower():
            accion_db = 'UPDATE'
        elif evento.tipo == 'INACTIVACION' or 'elimin' in evento.descripcion.lower() or 'bloqueo' in evento.descripcion.lower():
            accion_db = 'DELETE'

        logs_normalized.append({
            'icono': icono,
            'color': 'var(--primary)',
            'modulo': evento.modulo,
            'titulo': f"[{evento.modulo}] {evento.usuario}",
            'detalle': evento.descripcion,
            'fecha': evento.timestamp,
            'usuario': evento.usuario,
            'accion_db': accion_db
        })

    return render(request, 'auditoria/lista.html', {'full_logs': logs_normalized})

def usuarios_view(request):
    Usuario = get_user_model()
    usuarios_lista = Usuario.objects.all()
    return render(request, 'usuarios/lista.html', {'usuarios_lista': usuarios_lista})

@login_required
def ia_riesgos_view(request):
    try:
        from ia_analitica.motor import calcular_riesgos_globales
        analisis_riesgos, metrics = calcular_riesgos_globales()
    except Exception as e:
        logger.error(f"[ia_riesgos_view] Error al calcular riesgos: {e}", exc_info=True)
        analisis_riesgos = []
        metrics = {'promedio_global': 0.0, 'porcentaje_solventes': 0, 'tasa_reprobacion': 0}
    return render(request, 'ia_analitica/riesgo.html', {'riesgos': analisis_riesgos, 'metrics': metrics})

@login_required
def nuevo_expediente_view(request):
    import random
    from django.utils import timezone
    hoy = timezone.now().strftime('%Y-%m-%d')
    codigo_azar = str(random.randint(1000000, 9999999))
    
    if request.method == 'POST':
        # Extracción de datos del formulario virtual
        nombres = request.POST.get('nombres', '').strip().upper()
        apellidos = request.POST.get('apellidos', '').strip().upper()
        cedula = request.POST.get('cedula', '').strip()
        sexo = request.POST.get('sexo', '')

        # Normalizar fecha de nacimiento a YYYY-MM-DD (el input[type=date] ya devuelve ese formato)
        fecha_nac_raw = request.POST.get('fecha_nac', '').strip()
        fecha_nac = ''
        if fecha_nac_raw:
            from datetime import datetime as _dt
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
                try:
                    fecha_nac = _dt.strptime(fecha_nac_raw, fmt).strftime('%Y-%m-%d')
                    break
                except ValueError:
                    continue
            if not fecha_nac:
                fecha_nac = fecha_nac_raw  # Fallback: guardar como viene
        # Nuevos campos
        pais_nacimiento = request.POST.get('pais_nacimiento', 'Venezuela').strip()
        estado_nacimiento = request.POST.get('estado_nacimiento', '').strip()
        municipio_nacimiento = request.POST.get('municipio_nacimiento', '').strip()
        zona_educativa = request.POST.get('zona_educativa', '')
        codigo_plantel = request.POST.get('codigo_plantel', '')
        codigo_plan_estudio = request.POST.get('codigo_plan', '')
        ano_cursando = request.POST.get('ano_cursando', '1')
        seccion = request.POST.get('seccion', '').strip().upper()
        
        try:
            ano_cursando = int(ano_cursando)
        except ValueError:
            ano_cursando = 1
        
        # Datos del Representante
        nombre_rep = request.POST.get('nombre_representante', '').strip().upper()
        cedula_rep = request.POST.get('cedula_representante', '').strip().upper()
        tel_rep = request.POST.get('telefono_representante', '').strip()
        email_rep = request.POST.get('email_representante', '').strip()
        
        # Extracción de físicas (checkboxes)
        chk_cedula = request.POST.get('copia_cedula') == 'on'
        chk_partida = request.POST.get('partida_nacimiento') == 'on'
        chk_notas = request.POST.get('notas_viejas') == 'on'
        chk_fotos = request.POST.get('fotosp') == 'on'
        
        # Fechas de culminación académica
        mes_1 = request.POST.get('mes_culminacion_1er_ano', '').strip()
        ano_1 = request.POST.get('ano_culminacion_1er_ano', '').strip()
        mes_2 = request.POST.get('mes_culminacion_2do_ano', '').strip()
        ano_2 = request.POST.get('ano_culminacion_2do_ano', '').strip()
        mes_3 = request.POST.get('mes_culminacion_3er_ano', '').strip()
        ano_3 = request.POST.get('ano_culminacion_3er_ano', '').strip()
        mes_4 = request.POST.get('mes_culminacion_4to_ano', '').strip()
        ano_4 = request.POST.get('ano_culminacion_4to_ano', '').strip()
        mes_5 = request.POST.get('mes_culminacion_5to_ano', '').strip()
        ano_5 = request.POST.get('ano_culminacion_5to_ano', '').strip()
        
        # Contexto base de retorno en caso de error (para conservar campos ingresados)
        error_context = {
            'fecha_hoy': hoy,
            'random_codigo': codigo_azar,
            'nombres': nombres,
            'apellidos': apellidos,
            'cedula': cedula,
            'sexo': sexo,
            'fecha_nac': fecha_nac_raw,
            'pais_nacimiento': pais_nacimiento,
            'estado_nacimiento': estado_nacimiento,
            'municipio_nacimiento': municipio_nacimiento,
            'zona_educativa': zona_educativa,
            'codigo_plantel': codigo_plantel,
            'codigo_plan': codigo_plan_estudio,
            'ano_cursando': ano_cursando,
            'seccion': seccion,
            'nombre_representante': nombre_rep,
            'cedula_representante': cedula_rep,
            'telefono_representante': tel_rep,
            'email_representante': email_rep,
            'copia_cedula': chk_cedula,
            'partida_nacimiento': chk_partida,
            'notas_viejas': chk_notas,
            'fotosp': chk_fotos,
            'mes_culminacion_1er_ano': mes_1,
            'ano_culminacion_1er_ano': ano_1,
            'mes_culminacion_2do_ano': mes_2,
            'ano_culminacion_2do_ano': ano_2,
            'mes_culminacion_3er_ano': mes_3,
            'ano_culminacion_3er_ano': ano_3,
            'mes_culminacion_4to_ano': mes_4,
            'ano_culminacion_4to_ano': ano_4,
            'mes_culminacion_5to_ano': mes_5,
            'ano_culminacion_5to_ano': ano_5,
        }

        # ==============================================================
        # IA SEGURIDAD: Algoritmo de certificación de Integridad y Duplicidad
        # ==============================================================
        # Verificar duplicado en la base de datos
        if Estudiante.objects.filter(cedula_identidad=cedula).exists():
            error_context['error'] = f"Ya se encuentra registrado un integrante con la cédula V-{cedula}."
            return render(request, 'expedientes/nuevo.html', error_context)
            
        # Si la IA otorga luz verde, persistimos en PostgreSQL/SQLite
        try:
            nuevo_estudiante = Estudiante.objects.create(
                nombres=nombres,
                apellidos=apellidos,
                cedula_identidad=cedula,
                fecha_nacimiento=fecha_nac,
                sexo=sexo,
                pais_nacimiento=pais_nacimiento,
                estado_nacimiento=estado_nacimiento,
                municipio_nacimiento=municipio_nacimiento,
                zona_educativa=zona_educativa,
                codigo_plantel=codigo_plantel,
                codigo_plan_estudio=codigo_plan_estudio,
                ano_cursando=ano_cursando,
                seccion=seccion,
                nombre_representante=nombre_rep,
                cedula_representante=cedula_rep,
                telefono_representante=tel_rep,
                email_representante=email_rep,
                mes_culminacion_1er_ano=mes_1,
                ano_culminacion_1er_ano=ano_1,
                mes_culminacion_2do_ano=mes_2,
                ano_culminacion_2do_ano=ano_2,
                mes_culminacion_3er_ano=mes_3,
                ano_culminacion_3er_ano=ano_3,
                mes_culminacion_4to_ano=mes_4,
                ano_culminacion_4to_ano=ano_4,
                mes_culminacion_5to_ano=mes_5,
                ano_culminacion_5to_ano=ano_5,
            )
            
            exp = Expediente.objects.create(
                estudiante=nuevo_estudiante,
                copia_cedula=chk_cedula,
                partida_nacimiento=chk_partida,
                notas_certificadas_previas=chk_notas,
                fotografias=chk_fotos
            )
            exp.verificar_solvencia()
            
            from auditoria.models import registrar_evento
            registrar_evento(
                tipo='CREACION',
                descripcion=f'Se registró al estudiante {nuevo_estudiante.nombres} {nuevo_estudiante.apellidos} (V-{nuevo_estudiante.cedula_identidad}) y se abrió su expediente.',
                modulo='Expedientes',
                usuario=request.user.username,
                nivel_riesgo='INFORMATIVO'
            )
            
            from django.contrib import messages
            messages.success(request, f"Estudiante creado con éxito (V-{cedula}).")
            
            return render(request, 'expedientes/nuevo.html', {
                'success': True,
                'cedula_exitosa': cedula,
                'fecha_hoy': hoy,
                'random_codigo': str(random.randint(1000000, 9999999))
            })
        except Exception as e:
            error_context['error'] = f"Error crítico al intentar forzar escritura SQL: {str(e)}"
            return render(request, 'expedientes/nuevo.html', error_context)

    # Si es GET, se muestra el formulario vacío
    return render(request, 'expedientes/nuevo.html', {'fecha_hoy': hoy, 'random_codigo': codigo_azar})

@login_required
def detalle_expediente_view(request, cedula):
    import unicodedata as _ud
    import re as _re
    from django.shortcuts import get_object_or_404
    estudiante = get_object_or_404(Estudiante, cedula_identidad=cedula)
    expediente = getattr(estudiante, 'expediente', None)
    
    # ── Función de normalización canónica (sin acentos ni puntuación) ─────────
    def _canon(nombre):
        s = _ud.normalize('NFKD', str(nombre or '')).encode('ascii', 'ignore').decode('ascii')
        s = _re.sub(r'[^A-Za-z0-9 ]', ' ', s).upper()
        return _re.sub(r'\s+', ' ', s).strip()

    # ── 10 materias oficiales del plan de estudio (orden del formato) ─────────
    MATERIAS_OFICIALES = [
        ("LENGUA Y LITERATURA", ["LENGUA Y LITERATURA", "CASTELLANO", "LENGUA"]),
        ("IDIOMAS", ["IDIOMAS", "INGLÉS", "INGLÉS Y OTRAS LENGUAS EXTRANJERAS"]),
        ("MATEMÁTICA", ["MATEMÁTICA", "MATEMÁTICAS", "MATEMATICAS", "MATEMATICA"]),
        ("EDUCACIÓN FÍSICA", ["EDUCACIÓN FÍSICA", "EDUCACION FISICA"]),
        ("BIOLOGÍA, AMBIENTE Y TECNOLOGÍA", ["BIOLOGÍA, AMBIENTE Y TECNOLOGÍA", "BIOLOGIA, AMBIENTE Y TECNOLOGIA", "A.C.T.", "A.C.T", "CIENCIAS NATURALES"]),
        ("FÍSICA", ["FÍSICA", "FISICA"]),
        ("QUÍMICA", ["QUÍMICA", "QUIMICA"]),
        ("GEOGRAFÍA, HISTORIA Y SOBERANÍA NACIONAL", ["GEOGRAFÍA, HISTORIA , Y SOBERANÍA NACIONAL", "GEOGRAFÍA, HISTORIA Y SOBERANÍA NACIONAL", "GEOGRAFIA HISTORIA CIUDADANIA", "GEOGRAFIA, HISTORIA Y SOBERANIA NACIONAL"]),
        ("INNOVACIÓN TECNOLÓGICA Y PRODUCTIVA", ["INNOVACIÓN TECNOLÓGICA Y PRODUCTIVA", "I.T.P.", "I.T.P", "INNOVACION TECNOLOGICA Y PRODUCTIVA"]),
        ("ORIENTACIÓN VOCACIONAL", ["ORIENTACIÓN VOCACIONAL", "ORIENTACION VOCACIONAL"]),
    ]

    # Pre-calcular claves canónicas de cada sinónimo para búsqueda rápida
    _canon_map = {}  # canon_key -> display_name
    for display_name, aliases in MATERIAS_OFICIALES:
        for alias in aliases:
            _canon_map[_canon(alias)] = display_name

    # Obtenemos las calificaciones en crudo del historial SQL
    notas_raw = Calificacion.objects.filter(inscripcion__estudiante=estudiante).select_related('asignatura', 'inscripcion')
    
    # Mátriz de Construcción IA para organizar Años, Materias y Lapsos
    boleta_organizada = { 
        1: {'titulo': '1ER AÑO', 'materias': {}},
        2: {'titulo': '2DO AÑO', 'materias': {}},
        3: {'titulo': '3ER AÑO', 'materias': {}},
        4: {'titulo': '4TO AÑO', 'materias': {}},
        5: {'titulo': '5TO AÑO', 'materias': {}}
    }
    
    # ── Paso 1: Recopilar notas por nombre canónico dentro de cada año ────────
    # Estructura temporal: {año: {display_name: {l1, l2, l3, final}}}
    notas_por_ano = {}
    for calif in notas_raw:
        try:
            ano = int(calif.asignatura.ano_grado)
        except (ValueError, TypeError):
            continue
        if ano not in boleta_organizada:
            continue

        canon_key = _canon(calif.asignatura.nombre)
        display_name = _canon_map.get(canon_key, calif.asignatura.nombre)

        if ano not in notas_por_ano:
            notas_por_ano[ano] = {}
        if display_name not in notas_por_ano[ano]:
            notas_por_ano[ano][display_name] = {'l1': '-', 'l2': '-', 'l3': '-', 'final': '-'}

        tipo = str(calif.tipo).strip().upper()
        if tipo == 'DEF':
            notas_por_ano[ano][display_name]['final'] = calif.nota
        elif tipo == 'L1':
            notas_por_ano[ano][display_name]['l1'] = calif.nota
        elif tipo == 'L2':
            notas_por_ano[ano][display_name]['l2'] = calif.nota
        elif tipo == 'L3':
            notas_por_ano[ano][display_name]['l3'] = calif.nota

    # ── Paso 2: Para años 1-5, construir la lista completa de 10 materias ────
    from collections import OrderedDict
    for ano_num in range(1, 6):
        ano_notas = notas_por_ano.get(ano_num, {})
        materias_ordenadas = OrderedDict()
        idx = 0
        for display_name, _aliases in MATERIAS_OFICIALES:
            idx += 1
            if display_name in ano_notas:
                materias_ordenadas[f"of_{idx}"] = {
                    'nombre': display_name,
                    **ano_notas[display_name]
                }
            else:
                materias_ordenadas[f"of_{idx}"] = {
                    'nombre': display_name,
                    'l1': '-', 'l2': '-', 'l3': '-', 'final': '-'
                }
        # Añadir cualquier materia extra no oficial que tenga notas cargadas
        for extra_name, extra_data in ano_notas.items():
            if extra_name not in [dn for dn, _ in MATERIAS_OFICIALES]:
                idx += 1
                materias_ordenadas[f"ex_{idx}"] = {'nombre': extra_name, **extra_data}

        boleta_organizada[ano_num]['materias'] = materias_ordenadas


    # Calculo algorítmico de promedios
    for ano_num, ano_data in boleta_organizada.items():
        sum_l1 = sum_l2 = sum_l3 = sum_def = 0
        count_l1 = count_l2 = count_l3 = count_def = 0
        
        for mat in ano_data['materias'].values():
            if mat['l1'] != '-': sum_l1 += mat['l1']; count_l1 += 1
            if mat['l2'] != '-': sum_l2 += mat['l2']; count_l2 += 1
            if mat['l3'] != '-': sum_l3 += mat['l3']; count_l3 += 1
            if mat['final'] != '-': sum_def += mat['final']; count_def += 1
            
        ano_data['promedios'] = {
            'l1': round(sum_l1 / count_l1, 2) if count_l1 > 0 else '-',
            'l2': round(sum_l2 / count_l2, 2) if count_l2 > 0 else '-',
            'l3': round(sum_l3 / count_l3, 2) if count_l3 > 0 else '-',
            'final': round(sum_def / count_def, 2) if count_def > 0 else '-'
        }
                
    # Limpiamos la matriz para enviar al frontend (solo los años que tengan datos o todos vacios listos)
    # Determinar si el usuario actual puede eliminar calificaciones (solo Directora y Desarrollador)
    puede_eliminar = request.user.rol in ('ADMINISTRATIVO', 'DESARROLLADOR') if hasattr(request.user, 'rol') else False
    
    context = {
        'estudiante': estudiante,
        'expediente': expediente,
        'boleta': boleta_organizada,
        'puede_eliminar_calificaciones': puede_eliminar,
    }
    return render(request, 'expedientes/detalle.html', context)

@login_required
def editar_expediente_view(request, cedula):
    from django.shortcuts import get_object_or_404
    estudiante = get_object_or_404(Estudiante, cedula_identidad=cedula)
    expediente = getattr(estudiante, 'expediente', None)
    
    if request.method == 'POST':
        estudiante.nombres = request.POST.get('nombres', estudiante.nombres).strip().upper()
        estudiante.apellidos = request.POST.get('apellidos', estudiante.apellidos).strip().upper()
        
        fecha = request.POST.get('fecha_nac')
        if fecha:
            estudiante.fecha_nacimiento = fecha
            
        estudiante.sexo = request.POST.get('sexo', estudiante.sexo)
        estudiante.pais_nacimiento = request.POST.get('pais_nacimiento', estudiante.pais_nacimiento).strip()
        estudiante.estado_nacimiento = request.POST.get('estado_nacimiento', estudiante.estado_nacimiento).strip()
        estudiante.municipio_nacimiento = request.POST.get('municipio_nacimiento', estudiante.municipio_nacimiento).strip()
        
        try:
            estudiante.ano_cursando = int(request.POST.get('ano_cursando', estudiante.ano_cursando))
        except ValueError:
            pass
        estudiante.seccion = request.POST.get('seccion', estudiante.seccion).strip().upper()
        
        # Datos del Representante
        estudiante.nombre_representante = request.POST.get('nombre_representante', estudiante.nombre_representante).strip().upper()
        estudiante.cedula_representante = request.POST.get('cedula_representante', estudiante.cedula_representante).strip().upper()
        estudiante.telefono_representante = request.POST.get('telefono_representante', estudiante.telefono_representante).strip()
        estudiante.email_representante = request.POST.get('email_representante', estudiante.email_representante).strip()
        
        # Fechas de Culminación
        estudiante.mes_culminacion_1er_ano = request.POST.get('mes_culminacion_1er_ano', estudiante.mes_culminacion_1er_ano).strip()
        estudiante.ano_culminacion_1er_ano = request.POST.get('ano_culminacion_1er_ano', estudiante.ano_culminacion_1er_ano).strip()
        estudiante.mes_culminacion_2do_ano = request.POST.get('mes_culminacion_2do_ano', estudiante.mes_culminacion_2do_ano).strip()
        estudiante.ano_culminacion_2do_ano = request.POST.get('ano_culminacion_2do_ano', estudiante.ano_culminacion_2do_ano).strip()
        estudiante.mes_culminacion_3er_ano = request.POST.get('mes_culminacion_3er_ano', estudiante.mes_culminacion_3er_ano).strip()
        estudiante.ano_culminacion_3er_ano = request.POST.get('ano_culminacion_3er_ano', estudiante.ano_culminacion_3er_ano).strip()
        estudiante.mes_culminacion_4to_ano = request.POST.get('mes_culminacion_4to_ano', estudiante.mes_culminacion_4to_ano).strip()
        estudiante.ano_culminacion_4to_ano = request.POST.get('ano_culminacion_4to_ano', estudiante.ano_culminacion_4to_ano).strip()
        estudiante.mes_culminacion_5to_ano = request.POST.get('mes_culminacion_5to_ano', estudiante.mes_culminacion_5to_ano).strip()
        estudiante.ano_culminacion_5to_ano = request.POST.get('ano_culminacion_5to_ano', estudiante.ano_culminacion_5to_ano).strip()
        
        estudiante.save()
        
        if expediente:
            expediente.copia_cedula = request.POST.get('copia_cedula') == 'on'
            expediente.partida_nacimiento = request.POST.get('partida_nacimiento') == 'on'
            expediente.notas_certificadas_previas = request.POST.get('notas_viejas') == 'on'
            expediente.fotografias = request.POST.get('fotosp') == 'on'
            expediente.save()
            expediente.verificar_solvencia() # Actualizar estatus (Solvente/Incompleto)
            
        from auditoria.models import registrar_evento
        registrar_evento(
            tipo='MODIFICACION',
            descripcion=f'Se editaron los datos del estudiante {estudiante.nombres} {estudiante.apellidos} (V-{estudiante.cedula_identidad}).',
            modulo='Expedientes',
            usuario=request.user.username,
            nivel_riesgo='INFORMATIVO'
        )
            
        return redirect('expedientes')

    return render(request, 'expedientes/editar.html', {
        'estudiante': estudiante, 
        'expediente': expediente
    })

@login_required
def eliminar_expediente_view(request, cedula):
    from django.shortcuts import get_object_or_404
    from auditoria.models import registrar_evento
    from django.contrib import messages
    
    is_json = request.headers.get('Content-Type') == 'application/json' or request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if request.user.rol == 'PERSONAL':
        registrar_evento('BLOQUEO_DELETE', f'Intento de eliminar expediente V-{cedula}', 'Expedientes', request.user.username, 'CRITICO', False)
        if is_json:
            return JsonResponse({'ok': False, 'error': 'No tienes permisos para eliminar expedientes.'}, status=403)
        messages.error(request, 'No tienes permisos para eliminar expedientes.')
        return redirect('expedientes')

    estudiante = get_object_or_404(Estudiante, cedula_identidad=cedula)
    
    registrar_evento('INACTIVACION', f'Se eliminó el expediente de V-{cedula} ({estudiante.nombres})', 'Expedientes', request.user.username, 'MEDIO')
    
    try:
        if hasattr(estudiante, 'expediente'):
            estudiante.expediente.delete()  # Elimina el expediente físico y deja el log
        estudiante.delete() # Elimina el estudiante y deja log
        if is_json:
            return JsonResponse({'ok': True, 'mensaje': 'Expediente eliminado exitosamente.'})
        messages.success(request, 'Expediente eliminado exitosamente.')
    except Exception as e:
        logger.error(f"Error al eliminar expediente {cedula}: {e}", exc_info=True)
        if is_json:
            return JsonResponse({'ok': False, 'error': str(e)}, status=500)
        messages.error(request, f'Error al eliminar: {str(e)}')
    
    return redirect('expedientes')

@login_required
def eliminar_masivo_expedientes_view(request):
    import json
    from django.db import transaction as db_transaction
    from auditoria.models import registrar_evento
    from django.contrib import messages
    
    is_json = request.headers.get('Content-Type') == 'application/json' or request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.user.rol == 'PERSONAL':
        registrar_evento('BLOQUEO_DELETE', 'Intento de eliminación masiva de expedientes', 'Expedientes', request.user.username, 'CRITICO', False)
        if is_json:
            return JsonResponse({'ok': False, 'error': 'No tienes permisos para realizar esta acción.'}, status=403)
        messages.error(request, 'No tienes permisos para realizar esta acción.')
        return redirect('expedientes')

    if request.method == 'POST':
        cedulas = request.POST.getlist('estudiantes_seleccionados')
        
        if not cedulas and request.body:
            try:
                data = json.loads(request.body)
                cedulas = data.get('estudiantes_seleccionados', data.get('cedulas', data.get('ids', [])))
            except Exception:
                pass

        # Fallback de seguridad: si el frontend envió un array stringificado o separado por comas
        if isinstance(cedulas, list) and len(cedulas) == 1 and isinstance(cedulas[0], str):
            try:
                parsed = json.loads(cedulas[0])
                if isinstance(parsed, list):
                    cedulas = parsed
                else:
                    cedulas = [str(parsed)]
            except Exception:
                if ',' in cedulas[0]:
                    cedulas = [c.strip() for c in cedulas[0].split(',')]
                    
        # Garantizar que siempre sea una lista y que sus elementos sean strings limpios
        if not isinstance(cedulas, list):
            cedulas = [cedulas]
            
        cedulas = [str(c).strip() for c in cedulas if str(c).strip()]
            
        if cedulas:
            try:
                with db_transaction.atomic():
                    # Buscar estudiantes usando objects_all (incluye soft-deleted) para consistencia total
                    estudiantes_qs = Estudiante.objects_all.filter(cedula_identidad__in=cedulas)
                    eliminados_count = estudiantes_qs.count()
                    cedulas_reales = list(estudiantes_qs.values_list('cedula_identidad', flat=True))

                    if cedulas_reales:
                        # Eliminar expedientes primero (por seguridad, aunque CASCADE debería manejarlo)
                        Expediente.objects.filter(estudiante__cedula_identidad__in=cedulas_reales).delete()
                        # Hard delete definitivo de los estudiantes
                        Estudiante.objects_all.filter(cedula_identidad__in=cedulas_reales).delete()

                    registrar_evento(
                        'INACTIVACION',
                        f'Eliminación masiva definitiva: {eliminados_count} estudiantes ({", ".join(cedulas_reales[:10])}{"..." if len(cedulas_reales)>10 else ""})',
                        'Expedientes',
                        request.user.username,
                        'MEDIO',
                        detalle_json={'cedulas': cedulas_reales}
                    )
                    if is_json:
                        return JsonResponse({'ok': True, 'mensaje': f'Se eliminaron {eliminados_count} expedientes exitosamente.'})
                    messages.success(request, f'Se eliminaron {eliminados_count} expedientes exitosamente.')
            except Exception as e:
                logger.error(f"[eliminar_masivo] Error durante eliminación masiva: {e}", exc_info=True)
                if is_json:
                    return JsonResponse({'ok': False, 'error': f'Error al eliminar: {str(e)}'}, status=500)
                messages.error(request, f'Error al eliminar: {str(e)}')
        else:
            if is_json:
                return JsonResponse({'ok': False, 'error': 'No se seleccionaron expedientes para eliminar.'}, status=400)
            messages.warning(request, 'No se seleccionaron expedientes para eliminar.')
            
    return redirect('expedientes')

@login_required
def digitalizacion_masiva_view(request):
    import zipfile
    import re
    from django.core.files.base import ContentFile
    
    if request.method == 'POST' and request.FILES.get('archivo_zip'):
        zip_file = request.FILES['archivo_zip']
        # Bloqueamos archivos no-ZIP
        if not zip_file.name.lower().endswith('.zip'):
            return render(request, 'expedientes/carga_digital.html', {'error': 'Solo se admiten contenedores .zip por seguridad.'})
        
        procesados = 0
        errores = []

        try:
            with zipfile.ZipFile(zip_file, 'r') as z:
                # 1. Buscamos la cédula en el nombre del *.zip* en caso de que todo el ZIP pertenezca a un solo estudiante (Ej: 22041426.zip)
                cedula_global_match = re.search(r'(\d{7,9})', zip_file.name)
                cedula_global = cedula_global_match.group(1) if cedula_global_match else None
                
                for file_info in z.infolist():
                    # Ignorar directorios o archivos basura
                    if file_info.is_dir() or file_info.file_size == 0:
                        continue
                    
                    filename = file_info.filename.split('/')[-1].lower()
                    if not filename.endswith(('.jpg', '.jpeg', '.png')):
                        continue
                        
                    # 2. IA Lógica: Buscamos si la cédula está en el nombre del JPG (Ej: carnet_22041426.jpg)
                    cedula_match = re.search(r'(\d{7,9})', filename)
                    cedula = cedula_match.group(1) if cedula_match else cedula_global
                    
                    if not cedula:
                        errores.append(f"Imposible determinar Cédula de Identidad en: {filename}")
                        continue
                        
                    # Buscamos al estudiante en SQLite/PostgreSQL
                    estudiante_obj = Estudiante.objects.filter(cedula_identidad=cedula).first()
                    if not estudiante_obj:
                        errores.append(f"V-{cedula} inexistente en Base de Datos, descartando: {filename}")
                        continue
                        
                    if not hasattr(estudiante_obj, 'expediente'):
                        errores.append(f"V-{cedula} carece de Expediente, descartando documento físico.")
                        continue
                        
                    expediente = estudiante_obj.expediente
                    
                    # Leemos los bits originales
                    with z.open(file_info) as f:
                        file_content = f.read()
                        
                    # 3. Categorización del documento (Inteligencia Lógica robustecida con depuración de ruido)
                    django_file = ContentFile(file_content, name=filename)
                    nombre_base = filename.split('.')[0].lower()
                    letras_solo = re.sub(r'[^a-z]', '', nombre_base) # Filtramos números y símbolos para evaluar la raíz léxica
                    
                    if 'nacimiento' in letras_solo or 'partida' in letras_solo:
                        expediente.archivo_partida.save(f"partida_v{cedula}.jpg", django_file, save=False)
                        expediente.partida_nacimiento = True
                    elif 'nota' in letras_solo or 'certific' in letras_solo or 'nc' in letras_solo:
                        expediente.archivo_notas.save(f"notas_v{cedula}.jpg", django_file, save=False)
                        expediente.notas_certificadas_previas = True
                    elif 'carnet' in letras_solo or 'foto' in letras_solo:
                        img_temp = Image.open(BytesIO(file_content))
                        if img_temp.mode in ("RGBA", "P"):
                            img_temp = img_temp.convert("RGB")
                        
                        img_temp.thumbnail((400, 400), Image.Resampling.LANCZOS)
                        
                        output_io = BytesIO()
                        img_temp.save(output_io, format='WEBP', quality=80)
                        
                        webp_file = ContentFile(output_io.getvalue(), name=f"foto_v{cedula}.webp")
                        expediente.archivo_fotos.save(f"foto_v{cedula}.webp", webp_file, save=False)
                        expediente.fotografias = True
                    elif 'cedula' in letras_solo or 'ced' in letras_solo or 'ci' in letras_solo:
                        expediente.archivo_cedula.save(f"cedula_v{cedula}.jpg", django_file, save=False)
                        expediente.copia_cedula = True
                    else:
                        errores.append(f"Tipo documental desconocido en: {filename}")
                        continue
                        
                    expediente.save()
                    expediente.verificar_solvencia() # Esto actualiza su estatus a SOLVENTE o se mantiene en INCOMPLETO
                    procesados += 1
                    
            return render(request, 'expedientes/carga_digital.html', {
                'success': True,
                'procesados': procesados,
                'errores': errores
            })
            
        except Exception as e:
            return render(request, 'expedientes/carga_digital.html', {'error': f'Paquete defectuoso o corrupto: {str(e)}'})

    return render(request, 'expedientes/carga_digital.html')

def generar_titulo_view(request, cedula):
    from django.shortcuts import get_object_or_404
    from django.http import HttpResponse
    import os
    from django.conf import settings
    from PIL import Image, ImageDraw, ImageFont
    import datetime

    estudiante = get_object_or_404(Estudiante, cedula_identidad=cedula)
    
    # Ubicación donde el cliente debe guardar la plantilla
    plantillas_dir = os.path.join(settings.MEDIA_ROOT, 'plantillas')
    os.makedirs(plantillas_dir, exist_ok=True)
    
    # Soporte inteligente para PNG o JPG
    template_path = os.path.join(plantillas_dir, 'titulo_bachiller.png')
    if not os.path.exists(template_path):
        template_jpg = os.path.join(plantillas_dir, 'titulo_bachiller.jpg')
        if os.path.exists(template_jpg):
            template_path = template_jpg
    
    # Creamos un archivo vacio de contingencia si no metieron el diploma en la carpeta
    if not os.path.exists(template_path):
        img_error = Image.new('RGB', (1600, 1200), color=(255, 255, 255))
        draw_error = ImageDraw.Draw(img_error)
        draw_error.text((50, 50), "ERROR DE PLANTILLA NO ENCONTRADA", fill=(255,0,0))
        draw_error.text((50, 100), f"Por favor coloca la imagen del titulo en: {template_path}", fill=(0,0,0))
        img_error.save(template_path)
    
    # Usamos Inteligencia Pillow para pintar el lienzo
    img = Image.open(template_path)
    draw = ImageDraw.Draw(img)
    
    try:
        # Fuentes nativas de Windows para mejor estética
        font = ImageFont.truetype("arial.ttf", int(img.height * 0.020))
        font_bold = ImageFont.truetype("arialbd.ttf", int(img.height * 0.022))
    except Exception:
        font = ImageFont.load_default()
        font_bold = font

    W, H = img.size
    
    zona_educativa = estudiante.zona_educativa or "U.E.N Colegio Apacuana"
    codigo_plantel = estudiante.codigo_plantel or "OD24061508"
    plan_estudio = estudiante.codigo_plan_estudio or "-------"
    nombre_completo = f"{estudiante.nombres} {estudiante.apellidos}"
    cedula_text = f"{estudiante.cedula_identidad}"
    nacido_en = estudiante.estado_nacimiento or "NO ESPECIFICADO"
    fecha_nac = estudiante.fecha_nacimiento.strftime("%d/%m/%Y") if estudiante.fecha_nacimiento else ""
    fecha_hoy = datetime.datetime.now().strftime('%d/%m/%Y')
    lugar_expedicion = f"Charallave, {fecha_hoy}"
    anio_egreso = str(datetime.datetime.now().year)

    # Calculo IA paramétrico de Relaciones Espaciales Mátriz (X, Y) ENCAJADO
    draw.text((int(W * 0.380), int(H * 0.302)), zona_educativa, fill="black", font=font)       # Linea 1
    draw.text((int(W * 0.250), int(H * 0.330)), codigo_plantel, fill="black", font=font)       # Linea 2
    # Linea 3 es BACHILLER EN CIENCIAS
    draw.text((int(W * 0.410), int(H * 0.375)), plan_estudio, fill="black", font=font)         # Linea 4
    draw.text((int(W * 0.310), int(H * 0.398)), nombre_completo, fill="black", font=font_bold) # Linea 5
    draw.text((int(W * 0.417), int(H * 0.421)), cedula_text, fill="black", font=font_bold)     # Linea 6
    draw.text((int(W * 0.290), int(H * 0.445)), nacido_en, fill="black", font=font)            # Linea 7
    draw.text((int(W * 0.260), int(H * 0.470)), fecha_nac, fill="black", font=font)            # Linea 8
    # Linea 9 es texto genérico "Previo el cumplimiento..."
    draw.text((int(W * 0.405), int(H * 0.514)), lugar_expedicion, fill="black", font=font)     # Linea 10
    draw.text((int(W * 0.310), int(H * 0.537)), anio_egreso, fill="black", font=font_bold)     # Linea 11

    # Si la imagen originó como PNG con transparencia, la procesamos limpiamente
    img = img.convert('RGB')
    
    from auditoria.models import registrar_evento
    registrar_evento(
        tipo='CREACION',
        descripcion=f'Se emitió el título de bachiller para V-{estudiante.cedula_identidad} ({nombre_completo})',
        modulo='Expedientes',
        usuario=request.user.username,
        nivel_riesgo='MEDIO'
    )
    
    response = HttpResponse(content_type="image/png")
    img.save(response, "PNG", quality=100)
    # Genera visualización en vivo de alta resolución en web
    response['Content-Disposition'] = f'inline; filename="Titulo_V{cedula}.png"'
    return response

def guardar_observacion_view(request, cedula):
    from django.shortcuts import get_object_or_404
    import json
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    estudiante = get_object_or_404(Estudiante, cedula_identidad=cedula)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    
    asunto = data.get('asunto', '').strip()
    descripcion = data.get('descripcion', '').strip()
    
    if not asunto or not descripcion:
        return JsonResponse({'error': 'El asunto y la descripción son obligatorios.'}, status=400)
    
    from datetime import timedelta
    from django.utils import timezone
    
    # Prevenir envíos múltiples accidentales (guard de backend)
    reciente = ObservacionConductual.objects.filter(
        estudiante=estudiante,
        asunto=asunto,
        descripcion=descripcion,
        fecha_registro__gte=timezone.now() - timedelta(minutes=2)
    ).exists()
    
    if reciente:
        return JsonResponse({'error': 'Ya has registrado esta observación recientemente.'}, status=400)
    
    obs = ObservacionConductual.objects.create(
        estudiante=estudiante,
        asunto=asunto,
        descripcion=descripcion
    )
    
    from auditoria.models import registrar_evento
    registrar_evento(
        tipo='CREACION',
        descripcion=f'Se registró una observación conductual para V-{estudiante.cedula_identidad}: {asunto}',
        modulo='Expedientes',
        usuario=request.user.username,
        nivel_riesgo='MEDIO'
    )
    
    return JsonResponse({
        'ok': True,
        'id': obs.id,
        'asunto': obs.asunto,
        'descripcion': obs.descripcion,
    })

@login_required
@require_POST
def api_subir_foto_estudiante(request, cedula):
    from django.core.files.base import ContentFile
    estudiante = get_object_or_404(Estudiante, cedula_identidad=cedula)
    expediente, created = Expediente.objects.get_or_create(estudiante=estudiante)
    
    if 'foto' not in request.FILES:
        return JsonResponse({'ok': False, 'error': 'No se recibió ningún archivo de imagen.'}, status=400)
        
    foto_file = request.FILES['foto']
    try:
        file_content = foto_file.read()
        img_temp = Image.open(BytesIO(file_content))
        if img_temp.mode in ("RGBA", "P"):
            img_temp = img_temp.convert("RGB")
        
        img_temp.thumbnail((400, 400), Image.Resampling.LANCZOS)
        
        output_io = BytesIO()
        img_temp.save(output_io, format='WEBP', quality=80)
        
        webp_file = ContentFile(output_io.getvalue(), name=f"foto_v{cedula}.webp")
        expediente.archivo_fotos.save(f"foto_v{cedula}.webp", webp_file, save=False)
        expediente.fotografias = True
        expediente.save()
        expediente.verificar_solvencia()
        
        from auditoria.models import registrar_evento
        registrar_evento(
            tipo='MODIFICACION',
            descripcion=f'Se subió la foto de perfil para V-{cedula}. Se marcó automáticamente "Fotografías Carnet" como cargado.',
            modulo='Expedientes',
            usuario=request.user.username,
            nivel_riesgo='INFORMATIVO'
        )
        
        return JsonResponse({
            'ok': True,
            'mensaje': 'Foto subida exitosamente.',
            'url': expediente.archivo_fotos.url,
            'estatus': expediente.estatus
        })
    except Exception as e:
        logger.error(f"Error al procesar foto de estudiante: {e}", exc_info=True)
        return JsonResponse({'ok': False, 'error': f'Error al procesar la imagen: {str(e)}'}, status=500)

def generar_constancia_estudio_view(request, cedula):
    '''
    Genera la Constancia de Estudio como PDF renderizando directamente la plantilla
    Word (media/plantillas/ConstanciaEstudio.docx) vía docxtpl y docx2pdf.
    '''
    import datetime
    import os
    from django.shortcuts import get_object_or_404
    from django.http import HttpResponse
    from django.conf import settings
    from inscripciones.models import Inscripcion

    # ── Datos del estudiante ──────────────────────────────────────────────────
    estudiante = get_object_or_404(Estudiante, cedula_identidad=cedula)

    mapa_grados = {
        11: "1er Grado", 12: "2do Grado", 13: "3er Grado",
        14: "4to Grado", 15: "5to Grado", 16: "6to Grado",
        1: "1er Año", 2: "2do Año", 3: "3er Año",
        4: "4to Año", 5: "5to Año", 6: "Egresado/Graduado"
    }

    # PRIORIDAD: Información en tiempo real del perfil
    grado_text = mapa_grados.get(estudiante.ano_cursando, "Año no determinado")
    ahora_temp = datetime.datetime.now()
    a = ahora_temp.year
    periodo_escolar = f"{a}-{a+1}" if ahora_temp.month >= 8 else f"{a-1}-{a}"

    # Edad calculada dinámicamente desde fecha_nacimiento
    hoy = datetime.date.today()
    fn = estudiante.fecha_nacimiento
    edad_estudiante = (
        hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))
        if fn else "—"
    )

    # Fecha de emisión
    ahora = datetime.datetime.now()
    meses_str = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]

    # ── Contexto para la plantilla ────────────────────────────────────────────
    context = {
        'APELLIDOS_ESTUDIANTE': estudiante.apellidos,
        'NOMBRES_ESTUDIANTE':   estudiante.nombres,
        'cedula_estudiante':    estudiante.cedula_identidad,
        'edad_estudiante':      edad_estudiante,
        'lugar_nacimiento':     estudiante.lugar_nacimiento or 'NO ESPECIFICADO',
        'grado_ano':            grado_text,
        'nivel_educativo':      'Media General',
        'periodo_escolar':      periodo_escolar,
        'dia_emision':          str(ahora.day),
        'mes_emision':          meses_str[ahora.month - 1],
        'ano_emision':          str(ahora.year),
    }

    # ── Convertir con docxtpl y docx2pdf (Solo en Windows si están disponibles) ──
    pdf_generado = False
    pdf_data = None
    import sys

    if sys.platform == 'win32':
        try:
            from docxtpl import DocxTemplate
            from docx2pdf import convert
            import tempfile
            
            plantilla_docx = os.path.join(settings.MEDIA_ROOT, 'plantillas', 'ConstanciaEstudio.docx')
            if os.path.exists(plantilla_docx):
                doc = DocxTemplate(plantilla_docx)
                doc.render(context)
                
                temp_dir = tempfile.gettempdir()
                temp_docx_path = os.path.join(temp_dir, f"Constancia_{cedula}.docx")
                temp_pdf_path = os.path.join(temp_dir, f"Constancia_{cedula}.pdf")
                
                doc.save(temp_docx_path)
                
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                except ImportError:
                    pass
                    
                convert(temp_docx_path, temp_pdf_path)
                
                with open(temp_pdf_path, 'rb') as pdf_file:
                    pdf_data = pdf_file.read()
                    
                try:
                    os.remove(temp_docx_path)
                    os.remove(temp_pdf_path)
                except Exception:
                    pass
                    
                pdf_generado = True
        except Exception as e:
            # Si falla la conversión vía Word en Windows (ej. sin MS Word), registramos y procedemos al fallback
            print(f"Aviso: Falló la conversión vía Word en Windows ({e}). Usando fallback xhtml2pdf.")

    # ── Fallback robusto con xhtml2pdf (Garantizado para Render / Linux) ─────────
    if not pdf_generado:
        try:
            from xhtml2pdf import pisa
            from django.template.loader import get_template
            
            # Use direct file path for xhtml2pdf to avoid URI parsing issues in Windows
            logo_path = os.path.abspath(os.path.join(settings.MEDIA_ROOT, 'apacuana.png'))
            if sys.platform == 'win32':
                logo_path = logo_path.replace('\\', '/')
            context['logo_path'] = logo_path

            template = get_template('expedientes/constancia_estudio.html')
            html_string = template.render(context, request)

            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="Constancia_Estudio_V{cedula}.pdf"'

            pisa_status = pisa.CreatePDF(html_string, dest=response)
            if not pisa_status.err:
                return response
            else:
                return HttpResponse(
                    f"Error al generar el PDF vía xhtml2pdf: {pisa_status.err}",
                    status=500
                )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return HttpResponse(
                f"Error crítico al generar la constancia (intento con Word y xhtml2pdf fallidos): {str(e)}",
                status=500
            )

    response = HttpResponse(pdf_data, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Constancia_Estudio_V{cedula}.pdf"'
    return response

@login_required
def emitir_documento_formato_view(request, cedula, tipo_documento):
    import datetime
    import os
    import sys
    from django.shortcuts import get_object_or_404
    from django.http import HttpResponse, Http404
    from django.conf import settings
    from inscripciones.models import Inscripcion
    from xhtml2pdf import pisa
    from django.template.loader import get_template
    from django.template import TemplateDoesNotExist

    estudiante = get_object_or_404(Estudiante, cedula_identidad=cedula)
    mapa_grados = {
        11: "1er", 12: "2do", 13: "3er",
        14: "4to", 15: "5to", 16: "6to",
        1: "1er", 2: "2do", 3: "3er",
        4: "4to", 5: "5to", 6: "Egresado",
    }
    
    # PRIORIDAD: Información en tiempo real del perfil
    grado_text = mapa_grados.get(estudiante.ano_cursando, str(estudiante.ano_cursando))
    ahora_temp = datetime.datetime.now()
    a = ahora_temp.year
    periodo_escolar = f"{a}-{a+1}" if ahora_temp.month >= 8 else f"{a-1}-{a}"

    hoy = datetime.date.today()
    fn = estudiante.fecha_nacimiento
    edad_estudiante = (
        hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))
        if fn else "—"
    )

    meses_str = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]

    context = {
        'estudiante': estudiante,
        'apellidos': estudiante.apellidos,
        'nombres': estudiante.nombres,
        'cedula': estudiante.cedula_identidad,
        'edad': edad_estudiante,
        'lugar_nacimiento': estudiante.estado_nacimiento or 'NO ESPECIFICADO',
        'grado_ano': grado_text,
        'nivel_educativo': 'Media General',
        'periodo_escolar': periodo_escolar,
        'dia_emision': str(hoy.day),
        'mes_emision': meses_str[hoy.month - 1],
        'ano_emision': str(hoy.year),
        'ano_actual': str(hoy.year),
        'seccion': estudiante.seccion or '',
        'representante_nombre': estudiante.nombre_representante or "_______________________",
        'representante_cedula': estudiante.cedula_representante or "_______________________",
        'dia_reunion': request.GET.get('dia_reunion', '_______________________'),
        'hora_reunion': request.GET.get('hora_reunion', '_______'),
        'am_pm': request.GET.get('am_pm', ''),
        'docente_directivo': request.GET.get('docente_directivo', '_______________________________'),
        'fecha_asistencia': request.GET.get('fecha_asistencia', '__________________'),
        # ── NUEVAS VARIABLES CAPTURADAS DESDE EL FORMULARIO FRONTEND ──
        'numeral': request.GET.get('numeral', '_____'),
        'asunto': request.GET.get('asunto', 'el rendimiento académico'),
        # Variables Dinámicas para la Autoridad (Solución de conflicto)
        'nombre_autoridad': 'DIRECTIVA',
        'cargo_autoridad': 'U.E.N. APACUANA',
    }
    
    # Use direct file path for xhtml2pdf to avoid URI parsing issues in Windows
    logo_path = os.path.abspath(os.path.join(settings.MEDIA_ROOT, 'apacuana-logo.png'))
    if sys.platform == 'win32':
        logo_path = logo_path.replace('\\', '/')
    context['logo_path'] = logo_path

    import urllib.parse
    
    # Decodificar el tipo de documento de forma recursiva por si viene doble/múltiple codificado en URL
    doc_decoded = urllib.parse.unquote(tipo_documento)
    while '%' in doc_decoded:
        new_dec = urllib.parse.unquote(doc_decoded)
        if new_dec == doc_decoded:
            break
        doc_decoded = new_dec

    doc_decoded_stripped = doc_decoded.strip()
    names_to_try = [
        doc_decoded_stripped.replace(' ', '_'),
        doc_decoded_stripped.replace('_', ' '),
        doc_decoded_stripped
    ]
    
    template = None
    for name in names_to_try:
        try:
            template = get_template(f'formatos/{name}.html')
            break
        except TemplateDoesNotExist:
            continue
            
    if not template:
        # Fallback robusto escaneando el directorio de formatos
        formatos_dir = os.path.join(settings.BASE_DIR, 'templates', 'formatos')
        if os.path.exists(formatos_dir):
            target_norm = doc_decoded_stripped.lower().replace(' ', '').replace('_', '')
            for filename in os.listdir(formatos_dir):
                name_part, ext = os.path.splitext(filename)
                if ext.lower() == '.html':
                    file_norm = name_part.lower().replace(' ', '').replace('_', '')
                    if file_norm == target_norm:
                        template = get_template(f'formatos/{filename}')
                        break
                        
    if not template:
        raise Http404(f"Documento no encontrado en formatos. Se buscó original: '{tipo_documento}', decodificado: '{doc_decoded_stripped}'")

    html_string = template.render(context, request)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{tipo_documento}_V{cedula}.pdf"'

    # Agregado link_callback interno
    def local_link_callback(uri, rel):
        import os
        from django.conf import settings
        sUrl = settings.STATIC_URL
        sRoot = settings.STATIC_ROOT
        mUrl = settings.MEDIA_URL
        mRoot = settings.MEDIA_ROOT
        if uri.startswith(mUrl):
            path = os.path.join(mRoot, uri.replace(mUrl, ""))
        elif uri.startswith(sUrl):
            path = os.path.join(sRoot, uri.replace(sUrl, ""))
        else:
            return uri
        return path

    pisa_status = pisa.CreatePDF(html_string, dest=response, link_callback=local_link_callback)
    if not pisa_status.err:
        from auditoria.models import registrar_evento
        registrar_evento(
            tipo='CREACION',
            descripcion=f'Se emitió el documento "{tipo_documento}" en PDF para V-{estudiante.cedula_identidad}',
            modulo='Expedientes',
            usuario=request.user.username,
            nivel_riesgo='INFORMATIVO'
        )
        return response
    else:
        return HttpResponse(f"Error al generar el PDF: {pisa_status.err}", status=500)

@login_required
def generar_boleta_view(request, cedula):
    import datetime
    import os
    import sys
    import re
    import unicodedata
    from django.shortcuts import get_object_or_404
    from django.http import HttpResponse, Http404
    from django.conf import settings
    from django.template.loader import get_template
    from xhtml2pdf import pisa
    from estudiantes.models import Estudiante
    from inscripciones.models import Inscripcion, Asignatura
    from calificaciones.models import Calificacion

    estudiante = get_object_or_404(Estudiante, cedula_identidad=cedula)
    expediente = getattr(estudiante, 'expediente', None)

    # get request parameter or student's current year
    try:
        ano_grado = int(request.GET.get('ano', estudiante.ano_cursando))
    except (ValueError, TypeError):
        ano_grado = estudiante.ano_cursando

    if not (1 <= ano_grado <= 6):
        ano_grado = 1

    # Fetch enrollment
    inscripcion = Inscripcion.objects.filter(
        estudiante=estudiante,
        ano_grado=ano_grado
    ).order_by('-periodo__fecha_inicio').first()

    mapa_grados = {
        1: "1er Año", 2: "2do Año", 3: "3er Año",
        4: "4to Año", 5: "5to Año", 6: "Egresado/Graduado"
    }
    grado_text = mapa_grados.get(ano_grado, f"{ano_grado}° Año")

    if inscripcion:
        periodo_escolar = inscripcion.periodo.nombre
        seccion = inscripcion.seccion
    else:
        ahora_temp = datetime.datetime.now()
        a = ahora_temp.year
        periodo_escolar = f"{a}-{a+1}" if ahora_temp.month >= 8 else f"{a-1}-{a}"
        seccion = estudiante.seccion or "U"

    # Fetch qualifications
    if inscripcion:
        calificaciones = Calificacion.objects.filter(inscripcion=inscripcion).select_related('asignatura')
    else:
        calificaciones = Calificacion.objects.filter(inscripcion__estudiante=estudiante, asignatura__ano_grado=ano_grado).select_related('asignatura')

    # Subject matching function
    def clean_string(text):
        if not text:
            return ""
        text = "".join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
        text = re.sub(r'[^A-Z0-9\s]', '', text.upper())
        return re.sub(r'\s+', ' ', text).strip()

    # Get subjects in database for this year
    asignaturas_db = Asignatura.objects.filter(ano_grado=ano_grado)

    # 10 subjects of the format
    TABLA_FORMATO = [
        ("LENGUA Y LITERATURA", ["LENGUA Y LITERATURA", "LENGUA"]),
        ("IDIOMAS", ["IDIOMAS", "INGLES", "INGLÉS"]),
        ("MATEMATICA", ["MATEMATICA", "MATEMÁTICA"]),
        ("EDUCACION FISICA", ["EDUCACION FISICA", "EDUCACIÓN FÍSICA"]),
        ("AMBIENTE, CIENCIAS Y TECNOLOGIA", ["BIOLOGIA AMBIENTE Y TECNOLOGIA", "BIOLOGÍA AMBIENTE Y TECNOLOGÍA", "ACT", "AMBIENTE CIENCIAS Y TECNOLOGIA", "BIOLOGIA", "BIOLOGÍA", "CIENCIAS"]),
        ("FISICA", ["FISICA", "FÍSICA"]),
        ("QUIMICA", ["QUIMICA", "QUÍMICA"]),
        ("GEOGRAFIA, HISTORIA Y CIUDADANIA", ["GEOGRAFIA HISTORIA Y SOBERANIA NACIONAL", "GEOGRAFÍA HISTORIA Y SOBERANÍA NACIONAL", "GHC", "GEOGRAFIA", "GEOGRAFÍA"]),
        ("ORIENTACION VOCACIONAL", ["ORIENTACION VOCACIONAL", "ORIENTACIÓN VOCACIONAL", "ORIENTACION CONVIVENCIA", "ORIENTACIÓN CONVIVENCIA", "ORIENTACION", "ORIENTACIÓN"]),
        ("INNOVACION TECNOLOGICA Y PRODUCTIVA", ["INNOVACION TECNOLOGICA Y PRODUCTIVA", "INNOVACIÓN TECNOLÓGICA Y PRODUCTIVA", "INP", "ITP"])
    ]

    # Parse sin profesor parameters
    sin_profesor_map = {}
    for k, v in request.GET.items():
        if k.startswith('sp_mat_'):
            idx = k.split('_')[-1]
            mat_name = v
            lapso = request.GET.get(f'sp_lap_{idx}')
            if mat_name and lapso:
                mat_clean = clean_string(mat_name)
                if mat_clean not in sin_profesor_map:
                    sin_profesor_map[mat_clean] = []
                sin_profesor_map[mat_clean].append(lapso.upper())

    materias_boleta = []
    
    # Calculate grades
    sum_m1 = sum_m2 = sum_m3 = sum_def = 0
    count_m1 = count_m2 = count_m3 = count_def = 0

    for display_name, aliases in TABLA_FORMATO:
        # Find database asignatura matching aliases
        matching_db_ids = []
        for asig in asignaturas_db:
            asig_clean = clean_string(asig.nombre)
            if any(clean_string(alias) in asig_clean or asig_clean in clean_string(alias) for alias in aliases):
                matching_db_ids.append(asig.id)

        # Get grades for the matching database asignaturas
        m1_val = m2_val = m3_val = def_val = None
        for calif in calificaciones:
            if calif.asignatura_id in matching_db_ids:
                n = calif.nota
                val = int(n) if n.is_integer() else n
                if calif.tipo == 'L1':
                    m1_val = val
                elif calif.tipo == 'L2':
                    m2_val = val
                elif calif.tipo == 'L3':
                    m3_val = val
                elif calif.tipo == 'DEF':
                    def_val = val

        # Apply "S/P" (Sin Profesor) overrides
        lapsos_sp = []
        disp_clean = clean_string(display_name)
        if disp_clean in sin_profesor_map:
            lapsos_sp.extend(sin_profesor_map[disp_clean])
        else:
            # try matching aliases
            for alias in aliases:
                al_clean = clean_string(alias)
                if al_clean in sin_profesor_map:
                    lapsos_sp.extend(sin_profesor_map[al_clean])
                    break

        if 'M1' in lapsos_sp:
            m1_val = 'S/P'
        if 'M2' in lapsos_sp:
            m2_val = 'S/P'
        if 'M3' in lapsos_sp:
            m3_val = 'S/P'

        if m1_val is not None and m1_val != 'S/P':
            sum_m1 += m1_val
            count_m1 += 1
        if m2_val is not None and m2_val != 'S/P':
            sum_m2 += m2_val
            count_m2 += 1
        if m3_val is not None and m3_val != 'S/P':
            sum_m3 += m3_val
            count_m3 += 1
        if def_val is not None and def_val != 'S/P':
            sum_def += def_val
            count_def += 1

        materias_boleta.append({
            'nombre': display_name,
            'm1': m1_val if m1_val is not None else '-',
            'm2': m2_val if m2_val is not None else '-',
            'm3': m3_val if m3_val is not None else '-',
            'def': def_val if def_val is not None else '-'
        })

    # Averages
    promedios = {
        'm1': round(sum_m1 / count_m1, 2) if count_m1 > 0 else '-',
        'm2': round(sum_m2 / count_m2, 2) if count_m2 > 0 else '-',
        'm3': round(sum_m3 / count_m3, 2) if count_m3 > 0 else '-',
        'def': round(sum_def / count_def, 2) if count_def > 0 else '-'
    }

    # Prepare context
    logo_path = os.path.abspath(os.path.join(settings.MEDIA_ROOT, 'apacuana-logo.png'))
    if sys.platform == 'win32':
        logo_path = logo_path.replace('\\', '/')

    from auditoria.models import EventoAuditoria
    conteo_boletas = EventoAuditoria.objects.filter(
        tipo='CREACION',
        descripcion__startswith='Se emitió la Boleta de Calificaciones'
    ).count()
    numero_boleta = f"{conteo_boletas + 1:04d}"

    context = {
        'estudiante': estudiante,
        'apellidos': estudiante.apellidos,
        'nombres': estudiante.nombres,
        'cedula': estudiante.cedula_identidad,
        'grado_ano': grado_text,
        'seccion': seccion,
        'periodo_escolar': periodo_escolar,
        'logo_path': logo_path,
        'numero_expediente': expediente.numero_expediente if expediente else None,
        'numero_boleta': numero_boleta,
        'materias_boleta': materias_boleta,
        'promedios': promedios,
        'posicion': {'m1': '-', 'm2': '-', 'm3': '-'},
        'promedio_condecorado': request.GET.get('premio', ''),
        'orientacion_m1': '',
        'orientacion_m2': '',
        'orientacion_m3': '',
    }

    template = get_template('formatos/boleta_calificaciones.html')
    html_string = template.render(context, request)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Boleta_Calificaciones_V{cedula}.pdf"'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'

    def local_link_callback(uri, rel):
        sUrl = settings.STATIC_URL
        sRoot = settings.STATIC_ROOT
        mUrl = settings.MEDIA_URL
        mRoot = settings.MEDIA_ROOT
        if uri.startswith(mUrl):
            path = os.path.join(mRoot, uri.replace(mUrl, ""))
        elif uri.startswith(sUrl):
            path = os.path.join(sRoot, uri.replace(sUrl, ""))
        else:
            return uri
        return path

    pisa_status = pisa.CreatePDF(html_string, dest=response, link_callback=local_link_callback)
    if not pisa_status.err:
        from auditoria.models import registrar_evento
        registrar_evento(
            tipo='CREACION',
            descripcion=f'Se emitió la Boleta de Calificaciones en PDF para V-{estudiante.cedula_identidad}',
            modulo='Expedientes',
            usuario=request.user.username,
            nivel_riesgo='INFORMATIVO'
        )
        return response
    else:
        return HttpResponse(f"Error al generar el PDF de la Boleta: {pisa_status.err}", status=500)

def listar_observaciones_view(request, cedula):
    from django.shortcuts import get_object_or_404
    
    estudiante = get_object_or_404(Estudiante, cedula_identidad=cedula)

    observaciones = ObservacionConductual.objects.filter(estudiante=estudiante)
    
    data = []
    for obs in observaciones:
        data.append({
            'id': obs.id,
            'asunto': obs.asunto,
            'descripcion': obs.descripcion,
            'fecha': obs.fecha_registro.strftime('%d/%m/%Y %I:%M %p')
        })
    
    return JsonResponse({
        'estudiante': f'{estudiante.nombres} {estudiante.apellidos}',
        'cedula': estudiante.cedula_identidad,
        'observaciones': data
    })

def pdf_observacion_view(request, cedula, obs_id):
    from django.shortcuts import get_object_or_404
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    import io
    
    estudiante = get_object_or_404(Estudiante, cedula_identidad=cedula)
    observacion = get_object_or_404(ObservacionConductual, id=obs_id, estudiante=estudiante)
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.8*inch, bottomMargin=0.8*inch)
    styles = getSampleStyleSheet()
    elements = []
    
    # Título institucional
    titulo_style = ParagraphStyle('TituloIns', parent=styles['Title'], fontSize=14, spaceAfter=6, alignment=1)
    sub_style = ParagraphStyle('SubIns', parent=styles['Normal'], fontSize=10, alignment=1, textColor=colors.grey)
    
    elements.append(Paragraph('REPÚBLICA BOLIVARIANA DE VENEZUELA', titulo_style))
    elements.append(Paragraph('MINISTERIO DEL PODER POPULAR PARA LA EDUCACIÓN', sub_style))
    elements.append(Paragraph(estudiante.zona_educativa or 'U.E.N Colegio Apacuana', sub_style))
    elements.append(Spacer(1, 20))
    
    elements.append(Paragraph('INFORME DE ANÁLISIS CONDUCTUAL', ParagraphStyle('h2', parent=styles['Heading2'], alignment=1, textColor=colors.HexColor('#4F46E5'))))
    elements.append(Spacer(1, 15))
    
    # Datos del estudiante
    data_table = [
        ['Nombre Completo:', f'{estudiante.nombres} {estudiante.apellidos}'],
        ['Cédula de Identidad:', f'V-{estudiante.cedula_identidad}'],
        ['Fecha del Registro:', observacion.fecha_registro.strftime('%d/%m/%Y %I:%M %p')],
    ]
    t = Table(data_table, colWidths=[2*inch, 4*inch])
    t.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.lightgrey),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))
    
    # Asunto
    elements.append(Paragraph(f'<b>Asunto:</b> {observacion.asunto}', styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Descripción
    elements.append(Paragraph('<b>Descripción / Observaciones:</b>', styles['Normal']))
    elements.append(Spacer(1, 6))
    desc_style = ParagraphStyle('Desc', parent=styles['Normal'], fontSize=10, leading=14, borderWidth=1, borderColor=colors.lightgrey, borderPadding=10)
    elements.append(Paragraph(observacion.descripcion.replace('\n', '<br/>'), desc_style))
    
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Informe_Conductual_V{cedula}.pdf"'
    return response

def eliminar_observacion_view(request, cedula, obs_id):
    from django.shortcuts import get_object_or_404
    from auditoria.models import registrar_evento
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
        
    if request.user.rol == 'PERSONAL':
        registrar_evento('BLOQUEO_DELETE', f'Intento de eliminar observación conductual V-{cedula}', 'Expedientes', request.user.username, 'CRITICO', False)
        return JsonResponse({'error': 'No tienes permisos para eliminar observaciones.'}, status=403)
    
    estudiante = get_object_or_404(Estudiante, cedula_identidad=cedula)
    obs = get_object_or_404(ObservacionConductual, id=obs_id, estudiante=estudiante)
    
    registrar_evento('INACTIVACION', f'Se eliminó observación conductual de V-{cedula}: {obs.asunto}', 'Expedientes', request.user.username, 'MEDIO')
    
    obs.delete()
    
    return JsonResponse({'ok': True})
def notificar_representante_view(request, cedula, obs_id):
    estudiante = get_object_or_404(Estudiante, cedula_identidad=cedula)
    observacion = get_object_or_404(ObservacionConductual, id=obs_id, estudiante=estudiante)
    
    nombre_rep = estudiante.nombre_representante or "Representante"
    tel_rep = estudiante.telefono_representante
    email_rep = estudiante.email_representante
    
    mensaje = (
        f"Hola, buen día. Nos comunicamos con el Sr(a). {nombre_rep} del U.E.N Colegio Apacuana. "
        f"El(la) alumno(a) {estudiante.nombres} {estudiante.apellidos} (V-{estudiante.cedula_identidad}) "
        f"presenta la siguiente observación conductual: '{observacion.asunto}'. "
        f"Hacemos un llamado al representante para que se presente a la brevedad en la institución. "
        f"Muchas gracias y feliz día."
    )
    
    # 1. Enviar Correo (si existe)
    email_enviado = False
    if email_rep:
        try:
            send_mail(
                subject=f"CITACIÓN URGENTE: {estudiante.nombres} {estudiante.apellidos}",
                message=mensaje,
                from_email=None, # Usa DEFAULT_FROM_EMAIL de settings
                recipient_list=[email_rep],
                fail_silently=False,
            )
            email_enviado = True
        except Exception:
            pass
            
    # 2. Generar Link de WhatsApp/SMS
    wa_link = ""
    if tel_rep:
        # Limpiar teléfono (solo números)
        clean_tel = "".join(filter(str.isdigit, tel_rep))
        if not clean_tel.startswith('58') and (clean_tel.startswith('04') or clean_tel.startswith('4')):
            if clean_tel.startswith('0'): clean_tel = clean_tel[1:]
            clean_tel = '58' + clean_tel
        
        wa_link = f"https://wa.me/{clean_tel}?text={quote(mensaje)}"
        
    return JsonResponse({
        'ok': True,
        'email_enviado': email_enviado,
        'wa_link': wa_link,
        'mensaje_info': 'Notificación procesada exitosamente.'
    })

@login_required
def notas_docentes_view(request):
    """Vista administrativa: resumen de carga de notas por docente."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    from docentes.models import NotaEvaluacion, AsignacionDocente

    Usuario = get_user_model()
    query = request.GET.get('q', '').strip()

    docentes_qs = Usuario.objects.filter(rol='DOCENTE').order_by('username')
    if query:
        docentes_qs = docentes_qs.filter(
            Q(username__icontains=query) | Q(nombre_completo__icontains=query)
        )

    datos = []
    for doc in docentes_qs:
        notas_confirmadas = NotaEvaluacion.objects.filter(
            registrado_por=doc, es_borrador=False
        ).count()
        notas_borrador = NotaEvaluacion.objects.filter(
            registrado_por=doc, es_borrador=True
        ).count()
        asignaciones = AsignacionDocente.objects.filter(
            docente=doc, activa=True
        ).select_related('asignatura', 'periodo')[:5]

        if notas_confirmadas > 0:
            estado = 'COMPLETA'
        elif notas_borrador > 0:
            estado = 'BORRADOR'
        else:
            estado = 'SIN_CARGAR'

        ultima_nota = NotaEvaluacion.objects.filter(
            registrado_por=doc
        ).order_by('-fecha_registro').first()

        datos.append({
            'usuario': doc,
            'perfil': getattr(doc, 'perfil_docente', None),
            'notas_confirmadas': notas_confirmadas,
            'notas_borrador': notas_borrador,
            'asignaciones': asignaciones,
            'estado': estado,
            'ultima_actividad': ultima_nota.fecha_registro if ultima_nota else None,
        })

    return render(request, 'docentes/notas_docentes.html', {
        'datos': datos,
        'query': query,
        'total': len(datos),
    })


# ─── Módulo Actas ─────────────────────────────────────────────────────────────

@login_required
def actas_consejos_view(request):
    return render(request, 'actas/consejos_secciones.html')

@login_required
def actas_compromisos_view(request):
    return render(request, 'actas/compromisos.html')

@login_required
def actas_inasistencias_view(request):
    return render(request, 'actas/inasistencias.html')


@login_required
@require_POST
def auditoria_limpiar_view(request):
    if request.user.rol != 'DESARROLLADOR':
        return JsonResponse({'error': 'Acceso denegado. Solo el Desarrollador puede realizar esta acción.'}, status=403)
    
    try:
        from calificaciones.models import Calificacion
        from estudiantes.models import Expediente
        
        Calificacion.history.all().delete()
        Expediente.history.all().delete()
        
        try:
            from auditoria.models import EventoAuditoria
            EventoAuditoria.objects.all().delete()
        except Exception:
            pass
        
        # Opcionalmente otras tablas de historial
        try:
            from estudiantes.models import Estudiante, ObservacionConductual
            Estudiante.history.all().delete()
            ObservacionConductual.history.all().delete()
        except Exception:
            pass
            
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            User.history.all().delete()
        except Exception:
            pass

        try:
            from pagos.models import Personal, PagoPersonal, PeriodoPagoPersonal, DeudaEstudiante
            Personal.history.all().delete()
            PagoPersonal.history.all().delete()
            PeriodoPagoPersonal.history.all().delete()
            DeudaEstudiante.history.all().delete()
        except Exception:
            pass
            
        return JsonResponse({'ok': True, 'mensaje': 'Todos los logs de auditoría e historial de cambios han sido eliminados.'})
    except Exception as e:
        return JsonResponse({'error': f'Error al limpiar bitácora: {str(e)}'}, status=500)


# ─── API: EDITAR CALIFICACIÓN DE UNA MATERIA ──────────────────────────────────

@login_required
@require_POST
def api_editar_calificacion_view(request, cedula):
    """
    POST JSON: {ano_grado, materia_nombre, l1, l2, l3}
    Actualiza las calificaciones L1, L2, L3 y recalcula DEF para una materia
    específica de un estudiante en un año determinado.
    """
    import json
    import re as _re
    import unicodedata as _ud

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Datos JSON inválidos.'}, status=400)

    ano_grado = body.get('ano_grado')
    materia_nombre = body.get('materia_nombre', '').strip()
    l1_val = body.get('l1')
    l2_val = body.get('l2')
    l3_val = body.get('l3')

    if not ano_grado or not materia_nombre:
        return JsonResponse({'ok': False, 'error': 'Faltan campos obligatorios (ano_grado, materia_nombre).'}, status=400)

    try:
        ano_grado = int(ano_grado)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Año de grado inválido.'}, status=400)

    # Validar notas en rango 0-20, o guión/vacío para eliminar
    def _parse_nota(val):
        if val is None or val == '' or val == '-':
            return 'DELETE'
        try:
            # Reemplazar comas por puntos por si el usuario escribe con coma decimal
            val_str = str(val).replace(',', '.')
            f = float(val_str)
            if f != f:  # NaN
                return 'DELETE'
            if not (0 <= f <= 20):
                return 'INVALID'
            return round(f, 2)
        except (ValueError, TypeError):
            return 'INVALID'

    nota_l1 = _parse_nota(l1_val)
    nota_l2 = _parse_nota(l2_val)
    nota_l3 = _parse_nota(l3_val)

    if 'INVALID' in (nota_l1, nota_l2, nota_l3):
        return JsonResponse({'ok': False, 'error': 'Las notas deben estar entre 0 y 20, o ser "-" para dejarlas vacías.'}, status=400)

    # Buscar estudiante
    estudiante = Estudiante.objects.filter(cedula_identidad=cedula).first()
    if not estudiante:
        return JsonResponse({'ok': False, 'error': f'Estudiante V-{cedula} no encontrado.'}, status=404)

    # Buscar inscripción del año correspondiente
    from inscripciones.models import Inscripcion, Asignatura
    inscripcion = Inscripcion.objects.filter(
        estudiante=estudiante, ano_grado=ano_grado
    ).first()

    if not inscripcion:
        return JsonResponse({'ok': False, 'error': f'No se encontró inscripción para el año {ano_grado}.'}, status=404)

    # Normalizar nombre de materia para buscar la asignatura
    def _canon(nombre):
        s = _ud.normalize('NFKD', str(nombre or '')).encode('ascii', 'ignore').decode('ascii')
        s = _re.sub(r'[^A-Za-z0-9 ]', ' ', s).upper()
        return _re.sub(r'\s+', ' ', s).strip()

    # Buscar asignatura — intentar por nombre exacto y luego por canónico
    asignatura = Asignatura.objects.filter(
        nombre=materia_nombre, ano_grado=ano_grado
    ).first()

    if not asignatura:
        # Búsqueda por canonización
        canon_target = _canon(materia_nombre)
        for asig in Asignatura.objects.filter(ano_grado=ano_grado):
            if _canon(asig.nombre) == canon_target:
                asignatura = asig
                break

    if not asignatura:
        return JsonResponse({'ok': False, 'error': f'Asignatura "{materia_nombre}" no encontrada para {ano_grado}° año.'}, status=404)

    # Actualizar o eliminar calificaciones de lapsos
    notas_actualizadas = {}
    for tipo, nota_val in [('L1', nota_l1), ('L2', nota_l2), ('L3', nota_l3)]:
        if nota_val == 'DELETE':
            Calificacion.objects.filter(
                inscripcion=inscripcion,
                asignatura=asignatura,
                tipo=tipo
            ).delete()
            notas_actualizadas[tipo] = '-'
        else:
            obj, created = Calificacion.objects.update_or_create(
                inscripcion=inscripcion,
                asignatura=asignatura,
                tipo=tipo,
                defaults={'nota': nota_val}
            )
            notas_actualizadas[tipo] = nota_val

    # Recalcular o eliminar definitiva
    califs = Calificacion.objects.filter(
        inscripcion=inscripcion, asignatura=asignatura, tipo__in=['L1', 'L2', 'L3']
    )
    lapso_map = {c.tipo: c.nota for c in califs}
    notas_validas = [n for n in lapso_map.values() if n is not None]

    def_val = None
    if notas_validas:
        def_val = round(sum(notas_validas) / len(notas_validas), 2)
        Calificacion.objects.update_or_create(
            inscripcion=inscripcion,
            asignatura=asignatura,
            tipo='DEF',
            defaults={'nota': def_val}
        )
        notas_actualizadas['DEF'] = def_val
    else:
        Calificacion.objects.filter(
            inscripcion=inscripcion,
            asignatura=asignatura,
            tipo='DEF'
        ).delete()
        notas_actualizadas['DEF'] = '-'

    # Auditoría
    try:
        from auditoria.models import registrar_evento
        registrar_evento(
            tipo='MODIFICACION',
            descripcion=f'Se editaron calificaciones de {materia_nombre} ({ano_grado}° año) para V-{cedula}. Notas: {notas_actualizadas}',
            modulo='Calificaciones',
            usuario=request.user.username,
            nivel_riesgo='MEDIO'
        )
    except Exception:
        pass

    return JsonResponse({
        'ok': True,
        'mensaje': f'Calificaciones de "{materia_nombre}" actualizadas correctamente.',
        'notas': {
            'l1': lapso_map.get('L1', '-'),
            'l2': lapso_map.get('L2', '-'),
            'l3': lapso_map.get('L3', '-'),
            'final': def_val if def_val is not None else '-',
        }
    })


# ─── API: ELIMINAR CALIFICACIONES DE UN AÑO ──────────────────────────────────

@login_required
@require_POST
def api_eliminar_calificaciones_ano_view(request, cedula):
    """
    POST JSON: {ano_grado}
    Elimina todas las calificaciones de un estudiante para un año dado.
    Solo permitido para roles ADMINISTRATIVO (Directora) y DESARROLLADOR.
    """
    import json

    # Verificar permisos: solo ADMINISTRATIVO (Directora) y DESARROLLADOR
    rol = getattr(request.user, 'rol', None)
    if rol not in ('ADMINISTRATIVO', 'DESARROLLADOR'):
        return JsonResponse({
            'ok': False,
            'error': 'No tienes permisos para eliminar calificaciones. Solo la Directora y los Desarrolladores pueden realizar esta acción.'
        }, status=403)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Datos JSON inválidos.'}, status=400)

    ano_grado = body.get('ano_grado')
    if not ano_grado:
        return JsonResponse({'ok': False, 'error': 'Debe especificar el año a eliminar (ano_grado).'}, status=400)

    try:
        ano_grado = int(ano_grado)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Año de grado inválido.'}, status=400)

    # Buscar estudiante
    estudiante = Estudiante.objects.filter(cedula_identidad=cedula).first()
    if not estudiante:
        return JsonResponse({'ok': False, 'error': f'Estudiante V-{cedula} no encontrado.'}, status=404)

    # Buscar inscripción del año
    from inscripciones.models import Inscripcion
    inscripcion = Inscripcion.objects.filter(
        estudiante=estudiante, ano_grado=ano_grado
    ).first()

    if not inscripcion:
        return JsonResponse({'ok': False, 'error': f'No se encontraron calificaciones para el {ano_grado}° año.'}, status=404)

    # Contar y eliminar calificaciones
    count = Calificacion.objects.filter(inscripcion=inscripcion).count()
    if count == 0:
        return JsonResponse({'ok': False, 'error': 'No hay calificaciones cargadas para este año.'}, status=404)

    Calificacion.objects.filter(inscripcion=inscripcion).delete()

    # Auditoría
    try:
        from auditoria.models import registrar_evento
        label_ano = {1: '1er', 2: '2do', 3: '3er', 4: '4to', 5: '5to'}
        registrar_evento(
            tipo='INACTIVACION',
            descripcion=f'Se eliminaron {count} calificaciones del {label_ano.get(ano_grado, str(ano_grado))} Año para V-{cedula} ({estudiante.nombres} {estudiante.apellidos}).',
            modulo='Calificaciones',
            usuario=request.user.username,
            nivel_riesgo='CRITICO'
        )
    except Exception:
        pass

    return JsonResponse({
        'ok': True,
        'mensaje': f'Se eliminaron {count} calificaciones del {ano_grado}° año correctamente.',
        'eliminados': count
    })
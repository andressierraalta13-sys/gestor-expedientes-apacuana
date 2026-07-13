"""
Vista de Carga Masiva de Alumnos por Excel
Módulo: Calificaciones → Carga por Excel

Flujo:
  1. Usuario sube CARGA_MASIVA.xlsx
  2. ExcelParser analiza y extrae registros
  3. Sistema crea Estudiante + Expediente para nuevos alumnos
  4. Alumnos existentes se detectan sin duplicar (por cédula o nombre+fecha)
  5. Se calcula integridad de expedientes e informe de calidad

Flujo Definitiva Directa:
  1. Usuario sube formato_calificaciones.xlsx con hojas M1/M2/M3
  2. CalificacionesParser lee las 3 hojas (= Lapso 1, 2, 3)
  3. Se buscan estudiantes por cédula normalizada
  4. Se crean/actualizan Calificaciones L1, L2, L3 y DEF por materia
"""

import re
import logging
from django.shortcuts import render
from django.db import transaction
from estudiantes.models import Estudiante, Expediente
from inscripciones.models import Inscripcion, Asignatura, PeriodoAcademico
from calificaciones.models import Calificacion
from .excel_parser import ExcelParser
from .calificaciones_parser import CalificacionesParser, normalizar_cedula

logger = logging.getLogger(__name__)

NOMBRES_ANO = {
    11: '1er', 12: '2do', 13: '3er', 14: '4to', 15: '5to', 16: '6to',
    1: '1er', 2: '2do', 3: '3er', 4: '4to', 5: '5to'
}
LABEL_ANO   = {
    11: '1ER GRADO', 12: '2DO GRADO', 13: '3ER GRADO',
    14: '4TO GRADO', 15: '5TO GRADO', 16: '6TO GRADO',
    1: '1ER AÑO', 2: '2DO AÑO', 3: '3ER AÑO', 
    4: '4TO AÑO', 5: '5TO AÑO'
}


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _calcular_integridad(expediente, estudiante) -> dict:
    """Retorna campos faltantes y porcentaje de completitud del expediente."""
    faltantes = []
    if not expediente.copia_cedula:              faltantes.append('Copia C.I.')
    if not expediente.partida_nacimiento:        faltantes.append('Partida de Nacimiento')
    if not expediente.notas_certificadas_previas: faltantes.append('Notas Certificadas')
    if not expediente.fotografias:               faltantes.append('Fotografías')
    if not estudiante.nombre_representante:      faltantes.append('Nombre Representante')
    if not estudiante.telefono_representante:    faltantes.append('Teléfono Representante')
    if not estudiante.email_representante:       faltantes.append('Correo Representante')

    total = 7
    completados = total - len(faltantes)
    return {
        'faltantes':    faltantes,
        'completados':  completados,
        'total':        total,
        'porcentaje':   round((completados / total) * 100),
    }


def _buscar_duplicado(cedula: str, apellidos: str, nombres: str, fecha_nac) -> Estudiante | None:
    """
    Búsqueda inteligente de duplicados:
      1. Por cédula exacta — usa objects_all para detectar incluso alumnos hard-deleted.
      2. Si no hay cédula: apellidos + nombres + fecha_nacimiento.
    """
    if cedula:
        # Usar objects_all para evitar re-crear alumnos que ya existieron
        return Estudiante.objects_all.filter(cedula_identidad=cedula).first()

    if apellidos and nombres and fecha_nac:
        return Estudiante.objects_all.filter(
            apellidos__iexact=apellidos,
            nombres__iexact=nombres,
            fecha_nacimiento=fecha_nac,
        ).first()
    return None


# ─── VISTA PRINCIPAL ──────────────────────────────────────────────────────────

def carga_masiva_view(request):
    """
    Vista principal del módulo de Carga Masiva.
    Actúa como router según el campo 'modo' del formulario:
      - 'definitiva_directa' → procesa calificaciones multi-lapso
      - default              → carga masiva de alumnos (flujo original)
    """
    if request.method != 'POST' or not request.FILES.get('archivo_excel'):
        return render(request, 'calificaciones/carga_masiva.html')

    # Reset sequences if using PostgreSQL to avoid IntegrityError on PK
    from apps.calificaciones.excel_utils import reset_db_sequences
    reset_db_sequences()

    excel_file = request.FILES['archivo_excel']

    # Validación de formato
    if not excel_file.name.lower().endswith(('.xlsx', '.xls')):
        return render(request, 'calificaciones/carga_masiva.html', {
            'error': 'Formato no válido. Solo se aceptan archivos .xlsx o .xls'
        })

    # ── 1. PARSING IA ────────────────────────────────────────────────────────
    try:
        parser = ExcelParser(excel_file)
        resultado = parser.parse()
    except Exception as e:
        logger.error(f"[carga_masiva_view] Error en parser: {e}", exc_info=True)
        return render(request, 'calificaciones/carga_masiva.html', {
            'error': f'Error crítico en el motor de análisis: {str(e)}'
        })

    if not resultado.alumnos:
        return render(request, 'calificaciones/carga_masiva.html', {
            'error': 'El motor no encontró registros de alumnos en el archivo.',
            'diagnostico': resultado.diagnostico,
        })

    ano_grado = resultado.ano_grado_detectado
    ano_label = LABEL_ANO.get(ano_grado, 'AÑO NO DETERMINADO')

    # Detectar si hay alumnos de múltiples niveles (Primaria + Media)
    niveles = set()
    for alumno in resultado.alumnos:
        ac = alumno.get('ano_cursante')
        if ac is not None:
            if 11 <= ac <= 16:
                niveles.add('primaria')
            elif 1 <= ac <= 5:
                niveles.add('media')
    if len(niveles) > 1:
        ano_label = 'PRIMARIA Y MEDIA'

    # ── 2. PERSISTENCIA EN BASE DE DATOS ────────────────────────────────────
    cargados        = []   # Alumnos creados exitosamente
    ya_existentes   = []   # Alumnos que ya estaban en el sistema
    errores_filas   = []   # Filas con error de persistencia
    integridad_list = []   # Reporte de completitud por alumno

    with transaction.atomic():
        for alumno in resultado.alumnos:
            try:
                cedula     = alumno.get('cedula', '')
                apellidos  = alumno.get('apellidos', '')
                nombres    = alumno.get('nombres', '')
                fecha_nac  = alumno.get('fecha_nacimiento')

                # Detectar duplicado inteligente
                existente = _buscar_duplicado(cedula, apellidos, nombres, fecha_nac)

                if existente:
                    # Reactivar si estaba eliminado (soft-delete) y actualizar datos
                    hubo_cambios = False
                    if not existente.activo:
                        existente.activo = True
                        existente.fecha_inactivacion = None
                        hubo_cambios = True
                        
                    if alumno.get('ano_cursante'): 
                        existente.ano_cursando = alumno['ano_cursante']
                        hubo_cambios = True
                    elif ano_grado and not existente.ano_cursando:
                        existente.ano_cursando = ano_grado
                        hubo_cambios = True

                    if alumno.get('pais') and not existente.pais_nacimiento: existente.pais_nacimiento = alumno['pais']; hubo_cambios = True
                    if alumno.get('estado') and not existente.estado_nacimiento: existente.estado_nacimiento = alumno['estado']; hubo_cambios = True
                    if alumno.get('municipio') and not existente.municipio_nacimiento: existente.municipio_nacimiento = alumno['municipio']; hubo_cambios = True
                    if alumno.get('seccion'): existente.seccion = alumno['seccion']; hubo_cambios = True
                    if alumno.get('representante') and not existente.nombre_representante: existente.nombre_representante = alumno['representante']; hubo_cambios = True
                    if alumno.get('cedula_representante') and not existente.cedula_representante: existente.cedula_representante = alumno['cedula_representante']; hubo_cambios = True
                    if alumno.get('telefono') and not existente.telefono_representante: existente.telefono_representante = alumno['telefono']; hubo_cambios = True

                    if hubo_cambios:
                        existente.save()

                    # Calcular integridad del existente
                    try:
                        exp_existente = existente.expediente
                    except Exception:
                        exp_existente = Expediente.objects.create(estudiante=existente)
                        exp_existente.verificar_solvencia()

                    integridad = _calcular_integridad(exp_existente, existente)
                    ya_existentes.append({
                        'cedula':    existente.cedula_identidad,
                        'nombres':   existente.nombres,
                        'apellidos': existente.apellidos,
                        'integridad': integridad,
                    })
                    continue

                # Validación mínima para crear
                if not apellidos and not nombres:
                    errores_filas.append({
                        'fila':   alumno.get('fila_excel', '?'),
                        'motivo': 'Sin nombre ni apellidos suficientes para crear registro.',
                    })
                    continue

                # Cédula placeholder si no tiene
                import uuid
                cedula_guardada = cedula if cedula else f"SC-{alumno.get('fila_excel', '0')}-{uuid.uuid4().hex[:4]}"

                # Fecha fallback
                from datetime import date
                fecha_guardada = fecha_nac if fecha_nac else date(2000, 1, 1)

                # Crear Estudiante
                ano_final = alumno.get('ano_cursante') or ano_grado or 1
                nuevo = Estudiante.objects.create(
                    cedula_identidad=cedula_guardada,
                    nombres=nombres,
                    apellidos=apellidos,
                    fecha_nacimiento=fecha_guardada,
                    sexo=alumno.get('sexo', ''),
                    lugar_nacimiento=alumno.get('lugar_nacimiento', ''),
                    pais_nacimiento=alumno.get('pais', ''),
                    estado_nacimiento=alumno.get('estado', ''),
                    municipio_nacimiento=alumno.get('municipio', ''),
                    ano_cursando=ano_final,
                    seccion=alumno.get('seccion', ''),
                    nombre_representante=alumno.get('representante', ''),
                    cedula_representante=alumno.get('cedula_representante', ''),
                    telefono_representante=alumno.get('telefono', ''),
                )

                # Crear Expediente y asignar numero de expediente
                exp = Expediente.objects.create(
                    estudiante=nuevo,
                    numero_expediente=alumno.get('num_expediente', '')
                )
                exp.verificar_solvencia()

                # Calcular integridad
                integridad = _calcular_integridad(exp, nuevo)
                integridad_list.append({
                    'cedula':    cedula_guardada,
                    'nombres':   nombres,
                    'apellidos': apellidos,
                    'integridad': integridad,
                    'advertencias': alumno.get('advertencias', []),
                })

                cargados.append({
                    'cedula':    cedula_guardada,
                    'nombres':   nombres,
                    'apellidos': apellidos,
                    'ano':       LABEL_ANO.get(ano_final, ano_label),
                })

            except Exception as e:
                errores_filas.append({
                    'fila':   alumno.get('fila_excel', '?'),
                    'motivo': str(e),
                })

    # ── 3. RESUMEN GENERAL DE INTEGRIDAD ────────────────────────────────────
    todos_expedientes = integridad_list + [
        {
            'cedula':    e['cedula'],
            'nombres':   e['nombres'],
            'apellidos': e['apellidos'],
            'integridad': e['integridad'],
            'advertencias': [],
        }
        for e in ya_existentes if e.get('integridad')
    ]

    total_campos_prom = 0
    if todos_expedientes:
        total_campos_prom = round(
            sum(e['integridad']['porcentaje'] for e in todos_expedientes) / len(todos_expedientes)
        )

    # Auditoria
    if cargados or ya_existentes:
        from auditoria.models import registrar_evento
        registrar_evento(
            tipo='CREACION' if cargados else 'MODIFICACION',
            descripcion=f"Carga masiva procesada: {len(cargados)} nuevos, {len(ya_existentes)} existentes, {len(errores_filas)} errores.",
            modulo='Calificaciones',
            usuario=request.user.username,
            nivel_riesgo='MEDIO'
        )

    context = {
        'procesado':           True,
        'ano_label':           ano_label,
        'ano_grado':           ano_grado,
        'cargados':            cargados,
        'ya_existentes':       ya_existentes,
        'errores_filas':       errores_filas,
        'integridad_list':     todos_expedientes,
        'total_cargados':      len(cargados),
        'total_existentes':    len(ya_existentes),
        'total_errores':       len(errores_filas),
        'completitud_promedio': total_campos_prom,
        'diagnostico':         resultado.diagnostico,
        'calidad':             resultado.calidad,
    }
    return render(request, 'calificaciones/carga_masiva.html', context)



def notas_certificadas_view(request):
    """
    Vista principal del módulo de Notas Certificadas.
    Renderiza el template con la lista de expedientes ya generados.
    """
    from .models import NotaCertificada
    from django.db.utils import ProgrammingError, OperationalError
    
    try:
        expedientes = list(NotaCertificada.objects.all())
    except (ProgrammingError, OperationalError) as e:
        # Error común en producción si no se corrieron las migraciones (Render deploy)
        from django.http import HttpResponse
        return HttpResponse(
            f"<h2>Error de Base de Datos (500)</h2>"
            f"<p>Parece que las migraciones no se han aplicado en la base de datos de producción.</p>"
            f"<p><b>Detalle técnico:</b> {str(e)}</p>"
            f"<p>Por favor, asegúrate de que el comando de despliegue en Render ejecutó <code>python manage.py migrate</code>.</p>",
            status=500
        )
    except Exception as e:
        from django.http import HttpResponse
        return HttpResponse(f"<h2>Error Inesperado (500)</h2><p>{str(e)}</p>", status=500)

    return render(request, 'calificaciones/notas_certificadas.html', {
        'expedientes': expedientes,
    })


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _normalizar_cedula(valor) -> str:
    """Elimina comas, puntos, espacios y guiones; retorna solo dígitos."""
    import re
    if valor is None:
        return ''
    return re.sub(r'[^\d]', '', str(valor))


def _leer_celda(ws, row: int, col: int):
    """Lee valor de una celda (row/col 1-indexados) de forma segura."""
    cell = ws.cell(row=row, column=col)
    return cell.value


def _get_plantilla_path() -> str:
    """Retorna la ruta absoluta a la plantilla vacía oficial."""
    from django.conf import settings
    import os
    return os.path.join(settings.MEDIA_ROOT, 'plantillas', 'Notas certificadas vacias.xlsx')


# ─── VISTA: UPLOAD ─────────────────────────────────────────────────────────────

def notas_certificadas_upload_view(request):
    """
    POST: Recibe un archivo .xlsx (EJEMPLO), lee la hoja NCF, extrae la cédula 
    y calificaciones, rellena los datos del estudiante en la plantilla oficial
    y guarda el expediente generado.
    """
    import os
    from django.conf import settings
    from django.http import JsonResponse
    from django.views.decorators.csrf import csrf_exempt
    from .certificadas_generator import procesar_nota_certificada

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido.'}, status=405)

    archivo = request.FILES.get('archivo_xlsx')
    if not archivo:
        return JsonResponse({'ok': False, 'error': 'No se envió ningún archivo.'}, status=400)

    if not archivo.name.lower().endswith('.xlsx'):
        return JsonResponse({'ok': False, 'error': 'Solo se aceptan archivos .xlsx'}, status=400)

    try:
        usuario_nombre = request.user.username if request.user.is_authenticated else 'anónimo'
        nota_obj = procesar_nota_certificada(archivo, usuario_nombre)
        
        # Auditoría
        try:
            from auditoria.models import registrar_evento
            registrar_evento(
                tipo='CREACION',
                descripcion=f"Nota Certificada procesada y generada: {nota_obj.nombre_completo} (CI {nota_obj.cedula_normalizada}).",
                modulo='Notas Certificadas',
                usuario=usuario_nombre,
                nivel_riesgo='BAJO',
            )
        except Exception:
            pass

        return JsonResponse({
            'ok': True,
            'expediente': {
                'id':              nota_obj.pk,
                'nombre_completo': nota_obj.nombre_completo,
                'apellidos':       nota_obj.apellidos,
                'nombres':         nota_obj.nombres,
                'cedula':          nota_obj.cedula_normalizada,
                'fecha_carga':     nota_obj.fecha_carga.strftime('%d/%m/%Y %I:%M %p') if nota_obj.fecha_carga else '—',
            }
        })
    except Exception as e:
        import traceback
        return JsonResponse({
            'ok': False,
            'error': str(e),
            'detalles': traceback.format_exc()
        }, status=400)


# ─── VISTA: DESCARGA INDIVIDUAL ───────────────────────────────────────────────

def notas_certificadas_download_view(request, pk: int):
    """
    GET: Descarga el archivo .xlsx de un expediente individual.
    """
    from django.http import FileResponse, Http404
    from .models import NotaCertificada
    import os

    try:
        nota = NotaCertificada.objects.get(pk=pk)
    except NotaCertificada.DoesNotExist:
        raise Http404("Expediente no encontrado.")

    # Generar el PDF al vuelo usando la data actual, evitando usar Cloudinary
    from .certificadas_generator import generar_nota_certificada_pdf_automatica
    from django.http import HttpResponse

    try:
        _, pdf_bytes = generar_nota_certificada_pdf_automatica(nota.cedula_normalizada, request.user.username)
    except Exception as e:
        return HttpResponse(
            f"<h2>Error generando archivo (500)</h2><p>{str(e)}</p>", 
            status=500
        )

    nombre_descarga = f"NC_{nota.cedula_normalizada}_{nota.apellidos}.pdf"
    
    response = HttpResponse(
        pdf_bytes,
        content_type='application/pdf',
    )
    response['Content-Disposition'] = f'attachment; filename="{nombre_descarga}"'
    return response


# ─── VISTA: UNIFICACIÓN MASIVA ────────────────────────────────────────────────

def notas_certificadas_unificar_view(request):
    """
    POST JSON {ids: [1,2,3]}: Une múltiples expedientes en un solo libro Excel
    apilando verticalmente las hojas NCF y preservando exactamente el formato.
    """
    import json
    import io
    import copy
    from django.http import HttpResponse, JsonResponse
    from .models import NotaCertificada

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido.'}, status=405)

    try:
        body = json.loads(request.body)
        ids  = [int(i) for i in body.get('ids', [])]
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Datos inválidos.'}, status=400)

    if not ids:
        return JsonResponse({'ok': False, 'error': 'No se seleccionaron expedientes.'}, status=400)

    notas = NotaCertificada.objects.filter(pk__in=ids).order_by('fecha_carga')
    if not notas.exists():
        return JsonResponse({'ok': False, 'error': 'No se encontraron expedientes seleccionados.'}, status=404)

    try:
        from pypdf import PdfWriter

        merger = PdfWriter()

        for nota in notas:
            try:
                # Generamos al vuelo en memoria
                from .certificadas_generator import generar_nota_certificada_pdf_automatica
                _, pdf_bytes = generar_nota_certificada_pdf_automatica(nota.cedula_normalizada, request.user.username)
                merger.append(io.BytesIO(pdf_bytes))
            except Exception as e:
                logger.error(f"Error al generar nota de {nota.pk}: {e}")
                continue

        # ── Serializar a bytes y retornar como descarga ────────────────────────
        buffer = io.BytesIO()
        merger.write(buffer)
        buffer.seek(0)
        merger.close()

        response = HttpResponse(
            buffer.read(),
            content_type='application/pdf',
        )
        response['Content-Disposition'] = 'attachment; filename="Notas_Certificadas_Unificadas.pdf"'
        return response

    except Exception as e:
        logger.error(f"[unificar_view] Error: {e}", exc_info=True)
        return JsonResponse({'ok': False, 'error': f'Error al unificar: {str(e)}'}, status=500)


# ─── VISTA: ELIMINAR INDIVIDUAL/MASIVO ────────────────────────────────────────

def notas_certificadas_delete_view(request):
    """
    POST JSON {ids: [1,2,3]}: Elimina uno o más expedientes de notas certificadas.
    Borra tanto el registro en DB como el archivo físico asociado.
    Protegido para roles: ADMINISTRATIVO y DESARROLLADOR.
    """
    import json
    import os
    from django.http import JsonResponse
    from .models import NotaCertificada

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido.'}, status=405)

    if not request.user.is_authenticated or getattr(request.user, 'rol', None) not in ['ADMINISTRATIVO', 'DESARROLLADOR']:
        return JsonResponse({'ok': False, 'error': 'No tienes permisos para eliminar expedientes.'}, status=403)

    try:
        body = json.loads(request.body)
        ids = [int(i) for i in body.get('ids', [])]
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Datos inválidos.'}, status=400)

    if not ids:
        return JsonResponse({'ok': False, 'error': 'No se seleccionaron expedientes para eliminar.'}, status=400)

    notas = NotaCertificada.objects.filter(pk__in=ids)
    eliminados = 0
    fallidos = 0

    for nota in notas:
        try:
            if nota.archivo_pdf:
                nota.archivo_pdf.delete(save=False)
            nota.delete()
            eliminados += 1
        except Exception as e:
            logger.error(f"Error eliminando nota {nota.pk}: {e}")
            fallidos += 1

    return JsonResponse({
        'ok': True,
        'mensaje': f'Se eliminaron {eliminados} expedientes correctamente.' + (f' Hubo error en {fallidos}.' if fallidos else ''),
        'eliminados_ids': ids
    })

# ─── VISTA: GENERACIÓN AUTOMÁTICA DESDE PERFIL ────────────────────────────────

def emitir_notas_certificadas_auto_view(request, cedula):
    """
    GET: Genera y descarga automáticamente el documento de notas certificadas
    utilizando las calificaciones y fechas de culminación del perfil académico.
    """
    from django.http import FileResponse, Http404, HttpResponse
    from .certificadas_generator import generar_nota_certificada_pdf_automatica
    import os

    try:
        usuario_nombre = request.user.username if request.user.is_authenticated else 'anónimo'
        nota_obj, pdf_bytes = generar_nota_certificada_pdf_automatica(cedula, usuario_nombre)
        
        # Auditoría
        try:
            from auditoria.models import registrar_evento
            registrar_evento(
                tipo='CREACION',
                descripcion=f"Nota Certificada (Automática) generada: {nota_obj.nombre_completo} (CI {nota_obj.cedula_normalizada}).",
                modulo='Notas Certificadas',
                usuario=usuario_nombre,
                nivel_riesgo='BAJO',
            )
        except Exception:
            pass

        nombre_descarga = f"NC_Auto_{nota_obj.cedula_normalizada}_{nota_obj.apellidos}.pdf"

        response = HttpResponse(
            pdf_bytes,
            content_type='application/pdf',
        )
        response['Content-Disposition'] = f'inline; filename="{nombre_descarga}"'
        return response
    except Exception as e:
        import traceback
        error_msg = f"<h2>Error Inesperado (500)</h2><p>{str(e)}</p><pre>{traceback.format_exc()}</pre>"
        return HttpResponse(error_msg, status=500)


# ─── VISTA: GENERACIÓN AUTOMÁTICA EN EXCEL DESDE PERFIL ───────────────────────

def emitir_notas_certificadas_xlsx_view(request, cedula):
    """
    GET: Genera y descarga el documento de notas certificadas en formato Excel
    (.xlsx), usando la plantilla oficial vigente ('FORMATO EN BLANCO IMPRESION')
    rellenada con las calificaciones y fechas de culminación del perfil académico.
    Complementa a la emisión en PDF, que usa el mismo formato.
    """
    from django.http import HttpResponse
    from .certificadas_generator import generar_nota_certificada_automatica

    try:
        usuario_nombre = request.user.username if request.user.is_authenticated else 'anónimo'
        nota_obj, xlsx_bytes = generar_nota_certificada_automatica(cedula, usuario_nombre)

        # Auditoría
        try:
            from auditoria.models import registrar_evento
            registrar_evento(
                tipo='CREACION',
                descripcion=f"Nota Certificada (Excel) generada: {nota_obj.nombre_completo} (CI {nota_obj.cedula_normalizada}).",
                modulo='Notas Certificadas',
                usuario=usuario_nombre,
                nivel_riesgo='BAJO',
            )
        except Exception:
            pass

        nombre_descarga = f"NC_Auto_{nota_obj.cedula_normalizada}_{nota_obj.apellidos}.xlsx"

        response = HttpResponse(
            xlsx_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{nombre_descarga}"'
        return response
    except Exception as e:
        import traceback
        error_msg = f"<h2>Error Inesperado (500)</h2><p>{str(e)}</p><pre>{traceback.format_exc()}</pre>"
        return HttpResponse(error_msg, status=500)

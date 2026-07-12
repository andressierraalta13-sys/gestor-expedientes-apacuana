"""
Vista del módulo de Calificaciones (Notas Académicas por Excel)
Lógica: Sube un Excel con cédula + Lapso I/II/III + Definitiva por materia,
busca cada estudiante en BD y asocia las notas a su inscripción activa.
"""

import logging
from django.shortcuts import render
from django.db import transaction
from estudiantes.models import Estudiante
from inscripciones.models import Inscripcion, Asignatura, PeriodoAcademico
from calificaciones.models import Calificacion

from apps.calificaciones.excel_utils import pd

logger = logging.getLogger(__name__)

NOTA_MIN = 0.0
NOTA_MAX = 20.0


def _safe_float(val) -> float | None:
    """Convierte un valor a float válido en rango escolar venezolano (0–20)."""
    try:
        f = float(str(val).replace(',', '.').strip())
        if f != f:  # NaN check
            return None
        if not (NOTA_MIN <= f <= NOTA_MAX):
            return None
        return round(f, 2)
    except (ValueError, TypeError):
        return None


def _detectar_columnas(df_raw):
    """
    Detecta en las primeras 15 filas qué columna corresponde a cada campo.
    Retorna dict: {campo: col_index} y el índice de la fila de datos.
    Soporta modo vertical y modo horizontal (Sábana de Notas).
    """
    ALIASES = {
        'cedula':    ['CEDULA', 'CÉDULA', 'C.I', 'C.I.', 'CI', 'CED'],
        'materia':   ['MATERIA', 'ASIGNATURA', 'ASIG', 'MATERIAS'],
        'l1':        ['LAPSO I', 'LAPSO 1', 'L.I', 'L I', '1ER LAPSO', 'PRIMER LAPSO'],
        'l2':        ['LAPSO II', 'LAPSO 2', 'L.II', 'L II', '2DO LAPSO', 'SEGUNDO LAPSO'],
        'l3':        ['LAPSO III', 'LAPSO 3', 'L.III', 'L III', '3ER LAPSO', 'TERCER LAPSO'],
        'def':       ['DEFINITIVA', 'DEF', 'NOTA FINAL', 'FINAL', 'PROM'],
        'rep':       ['REPARACION', 'REPARACIÓN', 'REP'],
    }

    # MATERIAS COMUNES EN SABANAS
    MATERIAS_SABANA = [
        "LENGUA Y LITERATURA", "LENGUA", "IDIOMAS", "INGLES", "MATEMATICA", "EDUCACION FISICA",
        "A.C.T.", "FISICA", "QUIMICA", "GEOGRAFIA", "HISTORIA", "SOCIOLOGIA",
        "ORIENTACION", "I.T.P.", "BIOLOGIA", "CIENCIAS", "G.H.C", "ARTE", "PATRIMONIO"
    ]

    best_row, best_score = 0, 0
    all_keywords = [kw for aliases in ALIASES.values() for kw in aliases]

    for i in range(min(15, len(df_raw))):
        row_vals = [str(v).upper().strip() for v in df_raw.iloc[i]]
        score = sum(1 for kw in all_keywords if any(kw in cell for cell in row_vals))
        
        # Añadir score si encuentra materias en las columnas (formato matriz/sábana)
        sabana_hits = sum(1 for m in MATERIAS_SABANA if any(m in cell for cell in row_vals))
        score += sabana_hits
        
        if score > best_score:
            best_score = score
            best_row = i

    col_map = {}
    materias_cols = {}
    header_row = df_raw.iloc[best_row]
    
    for col_idx, cell in enumerate(header_row):
        text = str(cell).upper().strip()
        if not text or text == 'NAN': continue
        
        # Revisar campos estándar
        for field, aliases in ALIASES.items():
            if field not in col_map:
                if any(alias in text for alias in aliases):
                    col_map[field] = col_idx
                    break
        
        # Revisar materias como columnas
        for mat in MATERIAS_SABANA:
            if mat in text and col_idx not in col_map.values():
                materias_cols[col_idx] = text
                break

    # Determinar si es modo matriz (tiene varias materias pero no una columna unificadora de materias)
    if 'materia' not in col_map and len(materias_cols) >= 2:
        col_map['is_matrix'] = True
        col_map['materias_cols'] = materias_cols
    else:
        col_map['is_matrix'] = False

    return col_map, best_row + 1  # datos empiezan en la siguiente fila


def notas_calificaciones_view(request):
    """
    Módulo de carga de notas académicas por Excel.
    Formato esperado: cédula | materia | Lapso I | Lapso II | Lapso III | Definitiva
    """
    # Cargar períodos disponibles para el selector
    periodos_disponibles = PeriodoAcademico.objects.all().order_by('-fecha_inicio')

    if request.method != 'POST' or not request.FILES.get('archivo_excel'):
        return render(request, 'calificaciones/notas_calificaciones.html', {
            'periodos': periodos_disponibles,
        })

    excel_file = request.FILES['archivo_excel']

    if not excel_file.name.lower().endswith(('.xlsx', '.xls')):
        return render(request, 'calificaciones/notas_calificaciones.html', {
            'error': 'Solo se aceptan archivos .xlsx o .xls',
            'periodos': periodos_disponibles,
        })

    # 1. Detectar si el excel tiene hojas M1, M2, M3 (formato calificaciones Definitiva Directa)
    has_lapsos_sheets = False
    try:
        import openpyxl
        excel_file.seek(0)
        wb_temp = openpyxl.load_workbook(excel_file, read_only=True)
        sheet_names = wb_temp.sheetnames
        wb_temp.close()
        has_lapsos_sheets = any(s in sheet_names for s in ['M1', 'M2', 'M3'])
        excel_file.seek(0)
    except Exception as e:
        logger.warning(f"Error detectando hojas M1/M2/M3: {e}")

    # Obtener período seleccionado por el usuario o usar el activo por defecto
    periodo_id = request.POST.get('periodo_id', '').strip()
    if periodo_id:
        try:
            periodo = PeriodoAcademico.objects.get(id=int(periodo_id))
        except (PeriodoAcademico.DoesNotExist, ValueError):
            periodo = None
    else:
        periodo = PeriodoAcademico.objects.filter(activo=True).first()

    if not periodo:
        from datetime import date as dt_date
        periodo = PeriodoAcademico.objects.create(
            nombre='PERIODO ACTUAL',
            fecha_inicio=dt_date(2025, 1, 1),
            fecha_fin=dt_date(2028, 12, 30),
            activo=True
        )

    # Resultados
    cargadas        = []   # {'cedula', 'materia', 'notas_guardadas'}
    no_encontrados  = []   # {'cedula', 'fila'}
    errores         = []   # {'fila', 'motivo'}
    duplicados      = []   # {'cedula', 'materia', 'lapso'}

    # Leer el lapso destino seleccionado por el usuario en el frontend
    lapso_destino = request.POST.get('lapso_destino', 'DEF')

    if has_lapsos_sheets:
        # ═══ MODO MULTI-HOJA (M1, M2, M3) ═══
        from apps.calificaciones.calificaciones_parser import CalificacionesParser
        import re
        try:
            excel_file.seek(0)
            parser = CalificacionesParser(excel_file)
            resultado = parser.parse()
        except Exception as e:
            logger.error(f"[definitiva_directa] Error en parser: {e}", exc_info=True)
            return render(request, 'calificaciones/notas_calificaciones.html', {
                'error': f'Error crítico al analizar el archivo: {str(e)}',
                'periodos': periodos_disponibles,
            })

        if resultado.errores_globales:
            return render(request, 'calificaciones/notas_calificaciones.html', {
                'error': ' | '.join(resultado.errores_globales),
                'periodos': periodos_disponibles,
            })

        if not resultado.estudiantes:
            return render(request, 'calificaciones/notas_calificaciones.html', {
                'error': 'No se encontraron estudiantes con cédula válida en el archivo.',
                'periodos': periodos_disponibles,
            })

        # Pre-cargar estudiantes para optimizar
        cedula_to_estudiante = {}
        for est in Estudiante.objects_all.all():
            digits = re.sub(r'\D', '', est.cedula_identidad)
            cedula_to_estudiante[digits] = est

        ano_grado_input = request.POST.get('ano_grado', '').strip()
        ano_grado = int(ano_grado_input) if ano_grado_input.isdigit() else (resultado.ano_escolar or 1)

        with transaction.atomic():
            for cedula_norm, est_data in resultado.estudiantes.items():
                estudiante = cedula_to_estudiante.get(cedula_norm)
                if not estudiante:
                    no_encontrados.append({
                        'cedula': est_data.cedula_raw,
                        'fila': 'Excel',
                    })
                    continue

                if not estudiante.activo:
                    estudiante.activo = True
                    estudiante.fecha_inactivacion = None
                    estudiante.save()

                # Obtener o crear inscripción
                try:
                    inscripcion, _ = Inscripcion.objects.get_or_create(
                        estudiante=estudiante,
                        periodo=periodo,
                        defaults={
                            'ano_grado': ano_grado,
                            'seccion': resultado.seccion or 'U',
                        }
                    )
                except Exception as e:
                    errores.append({
                        'fila': 'Inscripción',
                        'motivo': f'V-{est_data.cedula_raw}: error al inscribir: {e}'
                    })
                    continue

                materias_procesadas = set()
                # {materia: {lapso: nota}} para el registro de cargadas y autocalcular DEF
                notas_por_materia = {}

                for lapso, materias_notas in est_data.notas.items():
                    for materia_canonica, nota_val in materias_notas.items():
                        materias_procesadas.add(materia_canonica)
                        if materia_canonica not in notas_por_materia:
                            notas_por_materia[materia_canonica] = {}
                        notas_por_materia[materia_canonica][lapso] = nota_val

                        # Buscar asignatura en BD
                        asignatura = Asignatura.objects.filter(
                            nombre=materia_canonica, ano_grado=ano_grado
                        ).first() or Asignatura.objects.filter(
                            nombre=materia_canonica, ano_grado=estudiante.ano_cursando
                        ).first()

                        if not asignatura:
                            # Crear asignatura con código seguro
                            import uuid
                            clean_name = re.sub(r'[^A-Z0-9]', '', materia_canonica)
                            safe_code = f"A{ano_grado}-{clean_name[:8]}-{uuid.uuid4().hex[:4]}".upper()
                            asignatura = Asignatura.objects.create(
                                nombre=materia_canonica,
                                ano_grado=ano_grado,
                                codigo=safe_code
                            )

                        existente = Calificacion.objects.filter(
                            inscripcion=inscripcion, asignatura=asignatura, tipo=lapso
                        ).first()

                        if existente:
                            if existente.nota != nota_val:
                                duplicados.append({
                                    'cedula': est_data.cedula_raw,
                                    'materia': materia_canonica,
                                    'lapso': lapso,
                                    'nota_anterior': existente.nota,
                                    'nota_nueva': nota_val,
                                })
                                existente.nota = nota_val
                                existente.save()
                        else:
                            Calificacion.objects.create(
                                inscripcion=inscripcion, asignatura=asignatura, tipo=lapso, nota=nota_val
                            )

                # Auto-calcular Definitiva si L1, L2 y L3 están completos
                for materia_canonica in materias_procesadas:
                    asignatura = Asignatura.objects.filter(
                        nombre=materia_canonica, ano_grado=ano_grado
                    ).first() or Asignatura.objects.filter(
                        nombre=materia_canonica, ano_grado=estudiante.ano_cursando
                    ).first()

                    if not asignatura:
                        continue

                    califs = Calificacion.objects.filter(
                        inscripcion=inscripcion, asignatura=asignatura, tipo__in=['L1', 'L2', 'L3']
                    )
                    lapso_map = {c.tipo: c.nota for c in califs}

                    if 'L1' in lapso_map and 'L2' in lapso_map and 'L3' in lapso_map:
                        def_val = round((lapso_map['L1'] + lapso_map['L2'] + lapso_map['L3']) / 3, 2)
                        def_existente = Calificacion.objects.filter(
                            inscripcion=inscripcion, asignatura=asignatura, tipo='DEF'
                        ).first()

                        if def_existente:
                            if def_existente.nota != def_val:
                                def_existente.nota = def_val
                                def_existente.save()
                        else:
                            Calificacion.objects.create(
                                inscripcion=inscripcion, asignatura=asignatura, tipo='DEF', nota=def_val
                            )
                        notas_por_materia[materia_canonica]['DEF'] = def_val

                # Formatear cargadas para el template
                for materia_canonica, lapsos in notas_por_materia.items():
                    notas_list = []
                    for k, v in sorted(lapsos.items()):
                        notas_list.append(f"{k}={v}")
                    cargadas.append({
                        'cedula': est_data.cedula_raw,
                        'alumno': f'{estudiante.apellidos} {estudiante.nombres}',
                        'materia': materia_canonica,
                        'notas': ', '.join(notas_list),
                        'notas_list': sorted(notas_list),
                    })

        context = {
            'procesado':         True,
            'cargadas':          cargadas,
            'no_encontrados':    no_encontrados,
            'errores':           errores,
            'duplicados':        duplicados,
            'total_notas':       len(cargadas),
            'total_no_enc':      len(no_encontrados),
            'total_errores':     len(errores),
            'total_duplicados':  len(duplicados),
            'col_map_detectado': ['M1 (Hojas Multi-Lapso)', 'M2', 'M3'],
            'periodo_usado':     periodo,
            'periodos':          periodos_disponibles,
        }
        return render(request, 'calificaciones/notas_calificaciones.html', context)

    else:
        # ═══ MODO ORIGINAL (Pandas single sheet) ═══
        try:
            df_raw = pd.read_excel(excel_file, header=None, dtype=str).fillna('')
        except Exception as e:
            return render(request, 'calificaciones/notas_calificaciones.html', {
                'error': f'Error al leer el archivo: {str(e)}',
                'periodos': periodos_disponibles,
            })

        col_map, data_start = _detectar_columnas(df_raw)

        # Validar que al menos haya cédula y una nota
        if 'cedula' not in col_map:
            return render(request, 'calificaciones/notas_calificaciones.html', {
                'error': 'No se detectó columna de Cédula. Verifica que el encabezado diga "CEDULA", "C.I." o similar.',
                'col_map_detectado': list(col_map.keys()),
                'periodos': periodos_disponibles,
            })

        # Obtener período seleccionado por el usuario o usar el activo por defecto
        periodo_id = request.POST.get('periodo_id', '').strip()
        if periodo_id:
            try:
                periodo = PeriodoAcademico.objects.get(id=int(periodo_id))
            except (PeriodoAcademico.DoesNotExist, ValueError):
                periodo = None
        else:
            periodo = PeriodoAcademico.objects.filter(activo=True).first()

        # Si no hay ningún período, crear uno por defecto
        if not periodo:
            from datetime import date as dt_date
            periodo = PeriodoAcademico.objects.create(
                nombre='PERIODO ACTUAL',
                fecha_inicio=dt_date(2025, 1, 1),
                fecha_fin=dt_date(2028, 12, 30),
                activo=True
            )


        # Resultados
        cargadas        = []   # {'cedula', 'materia', 'notas_guardadas'}
        no_encontrados  = []   # {'cedula', 'fila'}
        errores         = []   # {'fila', 'motivo'}
        duplicados      = []   # {'cedula', 'materia', 'lapso'}

        # Leer el lapso destino seleccionado por el usuario en el frontend
        lapso_destino = request.POST.get('lapso_destino', 'DEF')

        def get(row, field):
            col = col_map.get(field)
            if col is None or col >= len(row):
                return ''
            val = str(row.iloc[col]).strip()
            return '' if val.upper() in ('NAN', 'NONE', '') else val

        with transaction.atomic():
            for row_idx in range(data_start, len(df_raw)):
                row = df_raw.iloc[row_idx]

                # Filtro anti-basura
                non_empty = [str(v).strip() for v in row if str(v).strip() not in ('', 'nan')]
                if len(non_empty) < 2:
                    continue

                is_matrix = col_map.get('is_matrix', False)

                cedula_raw = get(row, 'cedula')
                cedula_str = str(cedula_raw).strip()
                if cedula_str.endswith('.0'):
                    cedula_str = cedula_str[:-2]
                import re
                cedula = re.sub(r'\D', '', cedula_str)
                if not cedula or len(cedula) < 6:
                    errores.append({'fila': row_idx + 1, 'motivo': f'Cédula inválida o vacía: "{cedula_raw}"'})
                    continue

                if not is_matrix:
                    materia_raw = get(row, 'materia')
                    if not materia_raw:
                        continue
                    materia = materia_raw.upper().strip()

                    # Filtro: fila de totales
                    skip_kw = ['PROMEDIO', 'TOTAL', 'FIRMA', 'DIRECTOR']
                    if any(kw in materia for kw in skip_kw):
                        continue

                # Buscar estudiante
                estudiante = Estudiante.objects.filter(cedula_identidad=cedula).first()
                if not estudiante:
                    no_encontrados.append({'cedula': cedula, 'fila': row_idx + 1})
                    continue

                # Obtener año grado del frontend o fallback
                ano_grado_input = request.POST.get('ano_grado', '').strip()
                if ano_grado_input.isdigit():
                    ano_grado = int(ano_grado_input)
                else:
                    ano_grado = estudiante.ano_cursando

                # Obtener o crear inscripción
                inscripcion, _ = Inscripcion.objects.get_or_create(
                    estudiante=estudiante,
                    periodo=periodo,
                    defaults={
                        'ano_grado': ano_grado,
                        'seccion': 'U'
                    }
                )
                
                if is_matrix:
                    # MODO SÁBANA DE NOTAS (Matricial)
                    materias_cols = col_map.get('materias_cols', {})
                    al_menos_una_nota = False
                    
                    for col_idx, materia_nombre in materias_cols.items():
                        materia = materia_nombre.replace('\n', ' ').upper().strip()
                        val = str(row.iloc[col_idx]).strip()
                        nota_val = _safe_float(val)
                        if nota_val is None:
                            continue
                            
                        al_menos_una_nota = True
                        notas_estudiante_guardadas = []
                        
                        import uuid
                        import re
                        clean_name = re.sub(r'[^A-Z0-9]', '', materia)
                        safe_code = f"A{ano_grado}-{clean_name[:8]}-{uuid.uuid4().hex[:4]}".upper()

                        # Obtener o crear asignatura
                        asignatura, _ = Asignatura.objects.get_or_create(
                            nombre=materia, ano_grado=ano_grado,
                            defaults={'codigo': safe_code}
                        )
                        
                        # Usamos el lapso seleccionado por el usuario (L1, L2, L3 o DEF)
                        tipo_nota = lapso_destino
                        
                        existente = Calificacion.objects.filter(inscripcion=inscripcion, asignatura=asignatura, tipo=tipo_nota).first()
                        if existente:
                            duplicados.append({
                                'cedula':  cedula, 'materia': materia, 'lapso': tipo_nota,
                                'nota_anterior': existente.nota, 'nota_nueva': nota_val,
                            })
                            existente.nota = nota_val
                            existente.save()
                        else:
                            Calificacion.objects.create(inscripcion=inscripcion, asignatura=asignatura, tipo=tipo_nota, nota=nota_val)
                        
                        notas_estudiante_guardadas.append(f'{tipo_nota}={nota_val}')
                        
                        # Auto-calcular Definitiva si están completos L1, L2, L3
                        califs = Calificacion.objects.filter(inscripcion=inscripcion, asignatura=asignatura, tipo__in=['L1', 'L2', 'L3'])
                        lapso_map = {c.tipo: c.nota for c in califs}
                        if 'L1' in lapso_map and 'L2' in lapso_map and 'L3' in lapso_map:
                            def_val = round((lapso_map['L1'] + lapso_map['L2'] + lapso_map['L3']) / 3, 2)
                            def_existente = Calificacion.objects.filter(inscripcion=inscripcion, asignatura=asignatura, tipo='DEF').first()
                            if def_existente:
                                if def_existente.nota != def_val:
                                    def_existente.nota = def_val
                                    def_existente.save()
                                    notas_estudiante_guardadas.append(f'DEF(Auto)={def_val}')
                            else:
                                Calificacion.objects.create(inscripcion=inscripcion, asignatura=asignatura, tipo='DEF', nota=def_val)
                                notas_estudiante_guardadas.append(f'DEF(Auto)={def_val}')
                                
                        # Añadir a cargadas por CADA materia (como en el modo vertical)
                        cargadas.append({
                            'cedula':      cedula,
                            'alumno':      f'{estudiante.apellidos} {estudiante.nombres}',
                            'materia':     materia,
                            'notas':       ', '.join(notas_estudiante_guardadas),
                            'notas_list':  notas_estudiante_guardadas,
                        })
                    
                    if not al_menos_una_nota:
                        errores.append({'fila': row_idx + 1, 'motivo': f'V-{cedula}: no se encontraron notas válidas en la matriz.'})
                        
                else:
                    # MODO VERTICAL TRADICIONAL
                    materia_raw = get(row, 'materia') or f'MATERIA_F{row_idx+1}'
                    materia = materia_raw.upper().strip()

                    # Filtro: fila de totales
                    skip_kw = ['PROMEDIO', 'TOTAL', 'FIRMA', 'DIRECTOR']
                    if any(kw in materia for kw in skip_kw):
                        continue

                    import uuid
                    import re
                    clean_name = re.sub(r'[^A-Z0-9]', '', materia)
                    safe_code = f"A{ano_grado}-{clean_name[:8]}-{uuid.uuid4().hex[:4]}".upper()

                    # Obtener o crear asignatura
                    asignatura, _ = Asignatura.objects.get_or_create(
                        nombre=materia,
                        ano_grado=ano_grado,
                        defaults={'codigo': safe_code}
                    )

                    # Procesar notas
                    notas_mapa = {
                        'L1':  _safe_float(get(row, 'l1')),
                        'L2':  _safe_float(get(row, 'l2')),
                        'L3':  _safe_float(get(row, 'l3')),
                        'DEF': _safe_float(get(row, 'def')),
                        'REP': _safe_float(get(row, 'rep')),
                    }

                    # Eliminamos la regla de "promedio parcial". 
                    # Ahora SOLO se calcula DEF si las 3 notas están completas. 
                    # (Pero lo hacemos después de guardar para chequear con BD también).
                    
                    notas_guardadas = []
                    for tipo, valor in notas_mapa.items():
                        if valor is None:
                            continue

                        # Detectar duplicado
                        existente = Calificacion.objects.filter(
                            inscripcion=inscripcion,
                            asignatura=asignatura,
                            tipo=tipo
                        ).first()

                        if existente:
                            duplicados.append({
                                'cedula':  cedula,
                                'materia': materia,
                                'lapso':   tipo,
                                'nota_anterior': existente.nota,
                                'nota_nueva': valor,
                            })
                            # Actualizar con el nuevo valor
                            existente.nota = valor
                            existente.save()
                        else:
                            Calificacion.objects.create(
                                inscripcion=inscripcion,
                                asignatura=asignatura,
                                tipo=tipo,
                                nota=valor,
                            )

                        notas_guardadas.append(f'{tipo}={valor}')

                    # Auto-calcular Definitiva si no fue proveída en el Excel pero están completos L1, L2, L3 (ya sea por este archivo o por BD)
                    if notas_mapa['DEF'] is None:
                        califs = Calificacion.objects.filter(inscripcion=inscripcion, asignatura=asignatura, tipo__in=['L1', 'L2', 'L3'])
                        lapso_map = {c.tipo: c.nota for c in califs}
                        if 'L1' in lapso_map and 'L2' in lapso_map and 'L3' in lapso_map:
                            def_val = round((lapso_map['L1'] + lapso_map['L2'] + lapso_map['L3']) / 3, 2)
                            def_existente = Calificacion.objects.filter(inscripcion=inscripcion, asignatura=asignatura, tipo='DEF').first()
                            if def_existente:
                                if def_existente.nota != def_val:
                                    def_existente.nota = def_val
                                    def_existente.save()
                                    notas_guardadas.append(f'DEF(Auto)={def_val}')
                            else:
                                Calificacion.objects.create(inscripcion=inscripcion, asignatura=asignatura, tipo='DEF', nota=def_val)
                                notas_guardadas.append(f'DEF(Auto)={def_val}')

                    if notas_guardadas:
                        cargadas.append({
                            'cedula':      cedula,
                            'alumno':      f'{estudiante.apellidos} {estudiante.nombres}',
                            'materia':     materia,
                            'notas':       ', '.join(notas_guardadas),   # string para fallback
                            'notas_list':  notas_guardadas,              # lista para el template
                        })
                    else:
                        errores.append({
                            'fila':   row_idx + 1,
                            'motivo': f'V-{cedula} / {materia}: todas las notas son inválidas o vacías.'
                        })

        context = {
            'procesado':         True,
            'cargadas':          cargadas,
            'no_encontrados':    no_encontrados,
            'errores':           errores,
            'duplicados':        duplicados,
            'total_notas':       len(cargadas),
            'total_no_enc':      len(no_encontrados),
            'total_errores':     len(errores),
            'total_duplicados':  len(duplicados),
            'col_map_detectado': list(col_map.keys()),
            'periodo_usado':     periodo,
            'periodos':          periodos_disponibles,
        }
        return render(request, 'calificaciones/notas_calificaciones.html', context)


def api_periodos_list_create(request):
    """
    API sencilla para listar y crear periodos académicos.
    """
    from django.http import JsonResponse
    import json
    
    if request.method == 'GET':
        periodos = PeriodoAcademico.objects.all().order_by('-fecha_inicio')
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
    from django.http import JsonResponse
    import json
    
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


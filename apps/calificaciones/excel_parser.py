"""
Motor IA de Parsing Adaptativo para Carga Masiva de Alumnos
Gestión de Expedientes Escolares - U.E.N. Colegio Apacuana

Diseñado para planillas administrativas venezolanas con estructura no normalizada.
Soporte: celdas combinadas, encabezados multi-fila, alias locales (F.N, L NAC, N C, etc.)
"""

import re
import logging
from datetime import datetime, date
from typing import Optional

from apps.calificaciones.excel_utils import pd

logger = logging.getLogger(__name__)

COLUMN_ALIASES = {
    'num_lista':        ['N°', 'NO.', 'NUM', 'LISTA', '#', 'NRO', 'ORD', 'ORDEN'],
    'cedula':           ['CEDULA', 'CÉDULA', 'C.I.', 'C. I.', 'CED'],
    'apellidos':        ['APELLIDOS', 'APELLIDO', 'APELL'],
    'nombres':          ['NOMBRES', 'NOMBRE', 'NOMB'],
    'nombre_completo':  ['NOMBRE COMPLETO NC', 'NOMBRE COMPLETO', 'ALUMNO', 'ESTUDIANTE', 'N C', 'NC'],
    'fecha_nacimiento': ['F.N.', 'F.N', 'F. N', 'FECHA NAC', 'FECHA DE NACIMIENTO',
                         'FECHA NACIMIENTO', 'FEC.NAC', 'F/N', 'FECHA NAC.', 'FECHA'],
    'dia_nac':          ['DIA', 'DÍA'],
    'mes_nac':          ['MES'],
    'ano_nacimiento':   ['AÑO NAC', 'AÑO DE NACIMIENTO', 'AÑO NACIMIENTO', 'AÑON', 'AÑO N', 'AÑO'],
    'sexo':             ['GENERO', 'GÉNERO', 'SEXO', 'SEX'],
    'lugar_nacimiento': ['LUGAR NAC', 'LUGAR DE NACIMIENTO', 'LUGAR DE NAC', 'LUGAR', 'LUGAR DE NAC.', 'LUG DE NAC', 'L.N.'],
    'pais':             ['PAIS DE NACIMIENTO', 'PAIS', 'PAÍS', 'NACIONALIDAD'],
    'estado':           ['ESTADO', 'ESTADO DE NACIMIENTO'],
    'municipio':        ['MUNICIPIO', 'MUNICIPIO DE NACIMIENTO'],
    'ano_cursante':     ['AÑO CURSANTE', 'ANO CURSANTE'],
    'grado_cursante':   ['GRADO CURSANTE', 'GRADO'],
    'seccion':          ['SECCIÓN', 'SECCION'],
    'representante':    ['REPRESENTANTE', 'NOMBRE REPRESENTANTE', 'NOMBRE DEL REPRESENTANTE'],
    'cedula_representante': ['CEDULA DEL REPRESENTANTE', 'CÉDULA DEL REPRESENTANTE', 'CI REPRESENTANTE', 'C.I. REPRESENTANTE', 'C.I REPRESENTANTE'],
    'telefono':         ['TELEFONO', 'TELÉFONO', 'TELEFONO REPRESENTANTE', 'TELÉFONO REPRESENTANTE', 'TELF'],
    # Campo de número/código de expediente escolar
    'num_expediente':   ['EXPEDIENTE', 'EXP', 'N° EXP', 'NRO EXP', 'NEXP', 'NUM EXP',
                         'NUMERO EXPEDIENTE', 'NÚMERO EXPEDIENTE', 'COD EXP', 'CODIGO EXPEDIENTE'],
}

# Palabras clave que indican que una fila es el encabezado real de la tabla
HEADER_KEYWORDS = [
    'CEDULA', 'CÉDULA', 'C.I', 'APELLIDOS', 'NOMBRES', 'SEXO', 'GENERO',
    'F.N', 'N C', 'LISTA', 'N°', 'NRO', 'NACIMIENTO', 'LUGAR', 'NOMBRE',
    'ESTADO', 'MUNICIPIO', 'AÑO CURSANTE', 'GRADO CURSANTE'
]

# Patrones de año académico detectables en cabeceras del documento
YEAR_PATTERNS_DOC = {
    '1ER': 1, '1RO': 1, 'PRIMERO': 1, 'PRIMER AÑO': 1,
    '2DO': 2, '2NDO': 2, 'SEGUNDO': 2, 'SEGUNDO AÑO': 2,
    '3ER': 3, '3RO': 3, 'TERCERO': 3, 'TERCER AÑO': 3,
    '4TO': 4, 'CUARTO': 4, 'CUARTO AÑO': 4,
    '5TO': 5, 'QUINTO': 5, 'QUINTO AÑO': 5,
}

# Patrones de grado para Primaria (códigos BD: 11-16)
GRADE_PATTERNS_DOC = {
    '1ER': 11, '1RO': 11, 'PRIMERO': 11, 'PRIMER GRADO': 11,
    '2DO': 12, '2NDO': 12, 'SEGUNDO': 12, 'SEGUNDO GRADO': 12,
    '3ER': 13, '3RO': 13, 'TERCERO': 13, 'TERCER GRADO': 13,
    '4TO': 14, 'CUARTO': 14, 'CUARTO GRADO': 14,
    '5TO': 15, 'QUINTO': 15, 'QUINTO GRADO': 15,
    '6TO': 16, 'SEXTO': 16, 'SEXTO GRADO': 16,
}

# Inferencia de año académico por rango de edad
YEAR_BY_AGE_RANGE = [
    (range(11, 13), 1),   # 11-12 años → 1er año
    (range(13, 15), 2),   # 13-14 años → 2do año
    (range(15, 17), 3),   # 15-16 años → 3er año
    (range(17, 19), 4),   # 17-18 años → 4to año
    (range(19, 22), 5),   # 19-21 años → 5to año
]

MESES_ES = {
    'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4, 'MAYO': 5, 'JUNIO': 6,
    'JULIO': 7, 'AGOSTO': 8, 'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12,
    'ENE': 1, 'FEB': 2, 'MAR': 3, 'ABR': 4, 'JUN': 6, 'JUL': 7,
    'AGO': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DIC': 12,
}

BASURA_KEYWORDS = [
    'PROMEDIO', 'TOTAL', 'FIRMA', 'DIRECTOR', 'SECRETARIA', 'SELLO',
    'OBSERVACIONES', 'APROBADO', 'REPROBADO', 'PROMOVIDO',
    'COMPLETO NOMBRE', 'NOMBRES APELLIDOS', 'EJEMPLO', 'MODELO',
    'NOMBRE Y APELLIDO', 'APELLIDOS Y NOMBRES', 'CÉDULA IDENTIDAD',
]

# ═══════════════════════════════════════════════════════════════
#  CONTENEDOR DE RESULTADOS
# ═══════════════════════════════════════════════════════════════
class ExcelParserResult:
    def __init__(self):
        self.alumnos = []
        self.ano_grado_detectado = None
        self.diagnostico = {
            'nivel_desorganizacion': 0,       # 0=ordenado, 1=moderado, 2=caótico
            'nivel_label': 'Ordenado',
            'total_filas_raw': 0,
            'filas_omitidas': 0,
            'columnas_detectadas': [],
            'columnas_faltantes': [],
            'header_row_index': None,
            'year_detection_method': 'No determinado',
            'advertencias': [],
        }
        self.calidad = {
            'total_registros': 0,
            'completos': 0,
            'incompletos': 0,
            'sin_cedula': 0,
            'sin_fecha_nac': 0,
            'porcentaje_completitud': 0.0,
            'edad_promedio': None,
            'rango_edades': None,
        }


# ═══════════════════════════════════════════════════════════════
#  MOTOR PRINCIPAL
# ═══════════════════════════════════════════════════════════════
class ExcelParser:
    """
    Motor IA de Parsing Adaptativo para planillas administrativas escolares venezolanas.
    Soporta estructura visual no normalizada, celdas combinadas y alias locales.
    """

    def __init__(self, file_object):
        self.file_object = file_object
        self.result = ExcelParserResult()
        self._df_raw = None
        self._col_map = {}
        self._header_row = None
        self._data_start_row = None
        self._hoja_tipo = None  # 'primaria', 'media', o None (flujo legacy)

    # ─── PUNTO DE ENTRADA ────────────────────────────────────────────────────
    def parse(self) -> ExcelParserResult:
        try:
            # Intentar lectura multi-hoja (Primaria / Media)
            sheets = pd.read_excel_all_sheets(self.file_object)
            nombres_hojas = [n.strip().upper() for n in sheets.keys()]
            tiene_primaria = any('PRIMARIA' in n for n in nombres_hojas)
            tiene_media = any('MEDIA' in n for n in nombres_hojas)

            if tiene_primaria or tiene_media:
                # ── Modo multi-hoja ──
                for sheet_name, df in sheets.items():
                    nombre_upper = sheet_name.strip().upper()
                    if 'PRIMARIA' in nombre_upper:
                        self._hoja_tipo = 'primaria'
                    elif 'MEDIA' in nombre_upper:
                        self._hoja_tipo = 'media'
                    else:
                        # Hoja no reconocida, saltar
                        self.result.diagnostico['advertencias'].append(
                            f'Hoja "{sheet_name}" ignorada (no es Primaria ni Media).'
                        )
                        continue

                    # Reset estado interno para cada hoja
                    self._df_raw = df.fillna('')
                    self._col_map = {}
                    self._header_row = None
                    self._data_start_row = None

                    self.result.diagnostico['total_filas_raw'] += len(self._df_raw)

                    self._fase1_detectar_ano_documental()
                    self._fase2_detectar_encabezado()
                    self._fase3_construir_mapa_columnas()
                    self._fase4_extraer_registros()

                    logger.info(f"[ExcelParser] Hoja '{sheet_name}' ({self._hoja_tipo}): "
                                f"{len(self.result.alumnos)} alumnos acumulados")

                # Fases finales sobre todos los alumnos acumulados
                self._hoja_tipo = None  # Reset para fases globales
                self._fase5_inferir_ano_por_edad()
                self._fase6_metricas_calidad()
            else:
                # ── Modo legacy (hoja única / sin nombres reconocidos) ──
                self._hoja_tipo = None
                self._fase0_cargar()
                self._fase1_detectar_ano_documental()
                self._fase2_detectar_encabezado()
                self._fase3_construir_mapa_columnas()
                self._fase4_extraer_registros()
                self._fase5_inferir_ano_por_edad()
                self._fase6_metricas_calidad()

        except Exception as e:
            logger.error(f"[ExcelParser] Error crítico: {e}", exc_info=True)
            self.result.diagnostico['advertencias'].append(f"Error crítico de motor: {str(e)}")
        return self.result

    # ─── FASE 0: CARGA ───────────────────────────────────────────────────────
    def _fase0_cargar(self):
        self._df_raw = pd.read_excel(self.file_object, header=None, dtype=str)
        self._df_raw = self._df_raw.fillna('')
        self.result.diagnostico['total_filas_raw'] = len(self._df_raw)

    # ─── FASE 1: DETECCIÓN DE AÑO EN CABECERAS DOCUMENTALES ─────────────────
    def _fase1_detectar_ano_documental(self):
        """Escanea las primeras 15 filas buscando menciones del año académico."""
        scan_limit = min(15, len(self._df_raw))
        for i in range(scan_limit):
            for val in self._df_raw.iloc[i]:
                text = str(val).upper().strip()
                for pattern, grado in YEAR_PATTERNS_DOC.items():
                    if pattern in text and self.result.ano_grado_detectado is None:
                        self.result.ano_grado_detectado = grado
                        self.result.diagnostico['year_detection_method'] = (
                            f'Cabecera documental fila {i}: "{str(val).strip()}"'
                        )
                        return

    # ─── FASE 2: DETECCIÓN ADAPTATIVA DEL ENCABEZADO ─────────────────────────
    def _fase2_detectar_encabezado(self):
        """
        Detecta la fila con mayor concentración de palabras clave de encabezado.
        Soporta encabezados desplazados hasta la fila 30.
        """
        scan_limit = min(30, len(self._df_raw))
        best_row, best_score = 0, 0

        for i in range(scan_limit):
            row_vals = [str(v).upper().strip() for v in self._df_raw.iloc[i]]
            score = sum(
                1 for kw in HEADER_KEYWORDS
                if any(kw in cell for cell in row_vals)
            )
            if score > best_score:
                best_score = score
                best_row = i

        self._header_row = best_row
        self._data_start_row = best_row + 1
        self.result.diagnostico['header_row_index'] = best_row

        # Nivel de desorganización
        if best_score < 2:
            nivel, label = 2, 'Caótico'
            self.result.diagnostico['advertencias'].append(
                "Encabezado no claro. Parsing en modo fallback."
            )
        elif best_row <= 3:
            nivel, label = 0, 'Ordenado'
        elif best_row <= 8:
            nivel, label = 1, 'Moderado'
        else:
            nivel, label = 2, 'Caótico'

        self.result.diagnostico['nivel_desorganizacion'] = nivel
        self.result.diagnostico['nivel_label'] = label

        # Detectar y saltar sub-encabezado (ej: DIA | MES | AÑO bajo F.N)
        # Solo saltar si la fila tiene MÁS DE 2 coincidencias con palabras de encabezado
        # (evitar omitir la primera fila de datos real)
        if self._data_start_row < len(self._df_raw):
            sub_row = self._df_raw.iloc[self._data_start_row]
            sub_row_text = ' '.join(str(v).upper() for v in sub_row)
            sub_keywords = ['DIA', 'MES', 'CALIFI', 'INASIS']
            hits = sum(1 for kw in sub_keywords if kw in sub_row_text)
            # Verificar que no sea un dato real (una cédula numérica larga invalida el skip)
            has_cedula_like = any(
                len(re.sub(r'\D', '', str(v))) >= 6
                for v in sub_row
            )
            if hits >= 2 and not has_cedula_like:
                self._data_start_row += 1

    # ─── FASE 3: MAPA DE COLUMNAS ─────────────────────────────────────────────
    def _fase3_construir_mapa_columnas(self):
        """
        Fusiona texto de hasta 3 filas de encabezado y mapea alias
        al índice de columna correspondiente.
        """
        if self._header_row is None:
            return

        n_cols = len(self._df_raw.columns)
        scan_end = min(self._header_row + 3, self._data_start_row)

        # Texto combinado por columna (hasta 3 filas encabezadoras)
        header_texts = {}
        for col_idx in range(n_cols):
            parts = []
            for row_i in range(self._header_row, scan_end):
                cell = str(self._df_raw.iloc[row_i, col_idx]).upper().strip()
                if cell and cell not in ('NAN', ''):
                    parts.append(cell)
            header_texts[col_idx] = ' '.join(parts)

        # Mapeo alias → columna (con coincidencia de palabra completa para evitar colisiones)
        def _match(alias, text):
            """Verifica si el alias aparece como palabra completa dentro del texto del encabezado."""
            return bool(re.search(r'(?<![A-ZÁÉÍÓÚÑ])' + re.escape(alias) + r'(?![A-ZÁÉÍÓÚÑ])', text))

        for field, aliases in COLUMN_ALIASES.items():
            for col_idx, text in header_texts.items():
                if col_idx in self._col_map.values() and field != 'cedula':
                    # No reasignar una columna ya mapeada (salvo para cédula que tiene prioridad)
                    pass
                for alias in aliases:
                    if _match(alias, text) and field not in self._col_map:
                        self._col_map[field] = col_idx
                        break

        detected = set(self._col_map.keys())
        self.result.diagnostico['columnas_detectadas'] = sorted(detected)
        self.result.diagnostico['columnas_faltantes'] = [
            f for f in COLUMN_ALIASES if f not in detected
        ]

    # ─── FASE 4: EXTRACCIÓN DE REGISTROS ─────────────────────────────────────
    def _fase4_extraer_registros(self):
        if self._data_start_row is None:
            return

        omitidos = 0
        for row_idx in range(self._data_start_row, len(self._df_raw)):
            row = self._df_raw.iloc[row_idx]
            registro = self._procesar_fila(row, row_idx)
            if registro is None:
                omitidos += 1
            else:
                self.result.alumnos.append(registro)

        self.result.diagnostico['filas_omitidas'] = omitidos

    def _procesar_fila(self, row, row_idx) -> Optional[dict]:
        def get(field):
            col = self._col_map.get(field)
            if col is None or col >= len(row):
                return ''
            val = str(row.iloc[col]).strip()
            return '' if val.upper() in ('NAN', 'NONE', '') else val

        # Filtro: fila casi vacía
        non_empty = [str(v).strip() for v in row if str(v).strip() not in ('', 'nan', 'NaN')]
        if len(non_empty) < 2:
            return None

        # Filtro: fila de totales/firmas/etiquetas de ejemplo
        combined = ' '.join(str(v).upper() for v in row)
        if any(kw in combined for kw in BASURA_KEYWORDS):
            return None

        # Filtro: Omite celdas que son puramente números de 4 dígitos (años) si no son cédulas
        # Si la fila tiene celdas que son exactamente '2026', '2027', etc., es un separador.
        for cell_val in row:
            cv = str(cell_val).strip()
            if cv in ('2026', '2027', '2028', '2029', '2030'):
                return None

        # Extracción base
        cedula_raw   = get('cedula')
        apellidos    = get('apellidos')
        nombres      = get('nombres')
        nombre_comp  = get('nombre_completo')
        sexo_raw     = get('sexo')
        lugar_nac    = get('lugar_nacimiento')
        pais         = get('pais') or 'VENEZUELA'
        num_lista    = get('num_lista')

        ano_cursante_raw   = get('ano_cursante')
        grado_cursante_raw = get('grado_cursante')
        seccion_raw        = get('seccion')
        estado_raw       = get('estado')
        municipio_raw    = get('municipio')
        representante    = get('representante')
        cedula_rep       = get('cedula_representante')
        telefono         = get('telefono')

        # Normalización y Validación de Patrón de Cédula
        digits_only = re.sub(r'\D', '', cedula_raw)
        # Si los dígitos de la cédula no son exactamente 8, lo descartamos
        if digits_only and len(digits_only) != 8:
            cedula_raw = ''

        # Protección extra: si la "cédula" parece una fecha y falló la validación
        if cedula_raw and ('/' in cedula_raw or '-' in cedula_raw) and len(digits_only) != 8:
            cedula_raw = ''

        # Normalización
        cedula = self._normalizar_cedula(cedula_raw)

        # Filtro: sin ningún dato personal mínimo o sin patrón de cédula/nombre
        if not cedula and not (apellidos or nombres or nombre_comp):
            return None

        # Separar nombre_completo si faltan apellidos/nombres
        if nombre_comp and not apellidos and not nombres:
            apellidos, nombres = self._split_nombre_completo(nombre_comp)
        elif apellidos and nombres and not nombre_comp:
            nombre_comp = f"{apellidos} {nombres}"

        apellidos   = self._limpiar_texto(apellidos)
        nombres     = self._limpiar_texto(nombres)
        nombre_comp = self._limpiar_texto(nombre_comp)
        sexo        = self._normalizar_sexo(sexo_raw)
        lugar_limpio = lugar_nac.strip() if len(lugar_nac.strip()) > 2 else ''

        # Fecha de nacimiento (multi-estrategia)
        fecha_nac = self._extraer_fecha(row, get)

        # Advertencias por registro
        adv = []
        if not cedula:         adv.append('Sin cédula (S/C)')
        if not fecha_nac:      adv.append('Sin fecha de nacimiento')
        if not apellidos:      adv.append('Sin apellidos')
        if not nombres:        adv.append('Sin nombres')

        return {
            'num_lista':        num_lista,
            'cedula':           cedula,
            'apellidos':        apellidos.upper(),
            'nombres':          nombres.upper(),
            'nombre_completo':  nombre_comp.upper(),
            'fecha_nacimiento': fecha_nac,
            'sexo':             sexo,
            'lugar_nacimiento': lugar_limpio.upper(),
            'pais':             pais.upper(),
            'estado':           self._limpiar_texto(estado_raw).upper(),
            'municipio':        self._limpiar_texto(municipio_raw).upper(),
            'ano_cursante':     self._resolver_ano_grado(ano_cursante_raw, grado_cursante_raw),
            'seccion':          seccion_raw.strip().upper()[:1] if seccion_raw else '',
            'representante':    self._limpiar_texto(representante).upper(),
            'cedula_representante': self._normalizar_cedula(cedula_rep),
            'telefono':         re.sub(r'\D', '', str(telefono)),
            'num_expediente':   get('num_expediente'),
            'advertencias':     adv,
            'fila_excel':       row_idx + 1,
        }

    # ─── FASE 5: INFERENCIA DE AÑO POR EDAD ──────────────────────────────────
    def _fase5_inferir_ano_por_edad(self):
        """Si el año no fue detectado documentalmente, infiere por edad promedio."""
        if self.result.ano_grado_detectado is not None:
            return

        anno_actual = datetime.now().year
        edades = []
        for alumno in self.result.alumnos:
            fn = alumno.get('fecha_nacimiento')
            if fn:
                edad = anno_actual - fn.year
                if 10 <= edad <= 22:
                    edades.append(edad)

        if not edades:
            self.result.diagnostico['advertencias'].append(
                "No se pudo inferir el año académico (sin fechas válidas)."
            )
            return

        edad_prom = sum(edades) / len(edades)
        for rango, grado in YEAR_BY_AGE_RANGE:
            if round(edad_prom) in rango:
                self.result.ano_grado_detectado = grado
                self.result.diagnostico['year_detection_method'] = (
                    f'Inferencia por edad promedio: {edad_prom:.1f} años → {grado}° Año'
                )
                return

        self.result.diagnostico['advertencias'].append(
            f"Edad promedio {edad_prom:.1f} fuera de rangos esperados. Año no determinado."
        )

    # ─── FASE 6: MÉTRICAS DE CALIDAD ─────────────────────────────────────────
    def _fase6_metricas_calidad(self):
        alumnos = self.result.alumnos
        total = len(alumnos)
        self.result.calidad['total_registros'] = total
        if total == 0:
            return

        sin_cedula  = sum(1 for a in alumnos if not a.get('cedula'))
        sin_fecha   = sum(1 for a in alumnos if not a.get('fecha_nacimiento'))
        con_adv     = sum(1 for a in alumnos if a.get('advertencias'))
        completos   = total - con_adv

        # Estadísticas de edad
        anno_actual = datetime.now().year
        edades = [
            anno_actual - a['fecha_nacimiento'].year
            for a in alumnos if a.get('fecha_nacimiento')
        ]
        edad_prom  = round(sum(edades) / len(edades), 1) if edades else None
        rango      = f"{min(edades)}–{max(edades)} años" if edades else None

        self.result.calidad.update({
            'completos':              completos,
            'incompletos':            con_adv,
            'sin_cedula':             sin_cedula,
            'sin_fecha_nac':          sin_fecha,
            'porcentaje_completitud': round((completos / total) * 100, 1),
            'edad_promedio':          edad_prom,
            'rango_edades':           rango,
        })

    # ─── HELPERS DE NORMALIZACIÓN ─────────────────────────────────────────────
    def _normalizar_cedula(self, raw: str) -> str:
        if not raw:
            return ''
        upper = raw.upper().strip()
        if any(x in upper for x in ('S/C', 'SC', 'S.C', 'SIN')):
            return ''
        digits = re.sub(r'\D', '', raw)
        return digits if len(digits) == 8 else ''

    def _normalizar_sexo(self, raw: str) -> str:
        upper = raw.upper().strip()
        if upper in ('M', 'MASC', 'MASCULINO', 'HOMBRE', 'H'):
            return 'M'
        if upper in ('F', 'FEM', 'FEMENINO', 'MUJER'):
            return 'F'
        return ''

    def _parse_ano_cursante(self, raw: str):
        """Parsea valor de 'AÑO CURSANTE' → código 1-5 (Media)."""
        if not raw:
            return None
        upper = str(raw).upper().strip()
        for pattern, grado in YEAR_PATTERNS_DOC.items():
            if pattern in upper:
                return grado
        try:
            val = int(float(raw))
            if 1 <= val <= 6:
                return val
        except (ValueError, TypeError):
            pass
        return None

    def _parse_grado_cursante(self, raw: str):
        """Parsea valor de 'GRADO CURSANTE' → código 11-16 (Primaria)."""
        if not raw:
            return None
        upper = str(raw).upper().strip()
        for pattern, codigo in GRADE_PATTERNS_DOC.items():
            if pattern in upper:
                return codigo
        try:
            val = int(float(raw))
            if 1 <= val <= 6:
                # Valor numérico crudo (1-6) en hoja Primaria → mapear a 10+val
                return 10 + val
        except (ValueError, TypeError):
            pass
        return None

    def _resolver_ano_grado(self, ano_cursante_raw: str, grado_cursante_raw: str):
        """
        Resuelve el código de año/grado según el tipo de hoja actual.
        Primaria → usa grado_cursante_raw (→ 11-16)
        Media    → usa ano_cursante_raw   (→ 1-5)
        Legacy   → intenta ambos en orden
        """
        if self._hoja_tipo == 'primaria':
            return self._parse_grado_cursante(grado_cursante_raw) if grado_cursante_raw else None
        elif self._hoja_tipo == 'media':
            return self._parse_ano_cursante(ano_cursante_raw) if ano_cursante_raw else None
        else:
            # Flujo legacy: intentar año primero, luego grado
            if ano_cursante_raw:
                resultado = self._parse_ano_cursante(ano_cursante_raw)
                if resultado:
                    return resultado
            if grado_cursante_raw:
                resultado = self._parse_grado_cursante(grado_cursante_raw)
                if resultado:
                    return resultado
            return None

    def _limpiar_texto(self, texto: str) -> str:
        if not texto:
            return ''
        return re.sub(r'[^\w\s\-\'\.]', '', texto, flags=re.UNICODE).strip()

    def _split_nombre_completo(self, nc: str) -> tuple:
        """Convención venezolana: primeras 2 palabras = apellidos, resto = nombres."""
        parts = nc.strip().split()
        if len(parts) >= 4:
            return ' '.join(parts[:2]), ' '.join(parts[2:])
        elif len(parts) == 3:
            return parts[0], ' '.join(parts[1:])
        elif len(parts) == 2:
            return parts[0], parts[1]
        return nc, ''

    def _extraer_fecha(self, row, get_fn) -> Optional[date]:
        """Multi-estrategia: campo directo → separado (dia/mes/año) → solo año."""
        # 1. Campo F.N directo
        fn_raw = get_fn('fecha_nacimiento')
        if fn_raw:
            f = self._parse_fecha_flexible(fn_raw)
            if f:
                return f

        # 2. Componentes separados
        dia = get_fn('dia_nac')
        mes = get_fn('mes_nac')
        ano = get_fn('ano_nacimiento')
        if dia or mes or ano:
            f = self._combinar_fecha(dia, mes, ano)
            if f:
                return f

        # 3. Solo año — Si hay una columna explícita de "año de nacimiento"
        # y es válido, usamos el 1 de enero de ese año como fallback seguro.
        if ano:
            try:
                a = int(float(ano))
                # Validamos que sea un año de nacimiento plausible (no un año escolar u otra basura)
                if 1990 <= a <= datetime.now().year:
                    return date(a, 1, 1)
            except (ValueError, TypeError):
                pass
        return None

    def _parse_fecha_flexible(self, raw: str) -> Optional[date]:
        raw = str(raw).strip()
        if not raw or raw.upper() in ('NAN', ''):
            return None

        # Excel serial date
        try:
            serial = float(raw)
            if 20000 < serial < 60000:
                from datetime import timedelta
                base = datetime(1899, 12, 30)
                return (base + timedelta(days=int(serial))).date()
        except ValueError:
            pass

        for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d/%m/%y', '%d.%m.%Y'):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue

        # "15 MARZO 2010" / "15 MAR 2010"
        m = re.match(r'(\d{1,2})\s+([A-Za-záéíóú]+)\s+(\d{4})', raw, re.IGNORECASE)
        if m:
            dia, mes_str, ano = m.groups()
            mes_num = MESES_ES.get(mes_str.upper()[:3])
            if mes_num:
                try:
                    return date(int(ano), mes_num, int(dia))
                except ValueError:
                    pass
        return None

    def _combinar_fecha(self, dia: str, mes: str, ano: str) -> Optional[date]:
        try:
            a = int(float(ano)) if ano else None
            if not a or not (1990 <= a <= 2020):
                return None
            d = max(1, min(31, int(float(dia)))) if dia else 1
            m = 1
            if mes:
                try:
                    m = int(float(mes))
                except ValueError:
                    m = MESES_ES.get(mes.upper()[:3], 1)
            return date(a, m if 1 <= m <= 12 else 1, d)
        except (ValueError, TypeError):
            return None

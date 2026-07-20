import os
import re
import unicodedata
from datetime import datetime
import openpyxl
from openpyxl.cell.cell import Cell
from django.conf import settings
from django.core.files.base import ContentFile
from io import BytesIO

from estudiantes.models import Estudiante
from inscripciones.models import PeriodoAcademico, Inscripcion, Asignatura
from calificaciones.models import Calificacion, NotaCertificada
from django.template.loader import render_to_string
from xhtml2pdf import pisa

ASIGNATURAS_PREDEFINIDAS = [
    "LENGUA Y LITERATURA", "IDIOMAS", "MATEMATICA", "MATEMÁTICA",
    "EDUCACION FISICA", "EDUACION FISICA", "EDUCACIÓN FÍSICA",
    "BIOLOGIA, AMBIENTE Y TECNOLOGIA", "BIOLOGÍA", "AMBIENTE Y TECNOLOGÍA",
    "FISICA", "FÍSICA", "QUIMICA", "QUÍMICA",
    "GEOGRAFIA, HISTORIA Y SOBERANIA NACIONAL", "GEOGRAFÍA, HISTORIA Y SOBERANÍA NACIONAL",
    "INNOVACION TECNOLOGICA Y PRODUCTIVA", "INNOVACION TECNOLOGIA Y PRODUCTIVIDAD",
    "ORIENTACION VOCACIONAL", "ORIENTACIÓN VOCACIONAL"
]

# ── Plantilla Excel oficial vigente ──────────────────────────────────────────
# Es la que aparece en "emitir documentos" del expediente. Reproduce EXACTAMENTE
# el formato de referencia 'EJEMPLO.xlsx' (hoja 'NCF'): mismas secciones
# ("Epónimo", "Centro de Desarrollo", "COMPONENTES DE FORMACIÓN…"), columnas
# (Nº/LETRAS/T-E/FECHA/PLANTEL) y firmas VII/VIII. La plantilla es la versión
# limpia y reutilizable generada por scripts/build_nc_ejemplo_template.py: se usa
# tal cual (bordes, celdas combinadas y estructura) y solo se rellenan los datos
# del estudiante, la institución (Apacuana) y las calificaciones.
PLANTILLA_XLSX = 'FORMATO NC EJEMPLO.xlsx'
HOJA_XLSX = 'NCF'

# ── Datos institucionales de Apacuana (se conserva el DISEÑO del formato nuevo,
#    pero con la identidad del plantel del sistema) ────────────────────────────
PLANTEL = {
    'nombre': 'U. E. N. APACUANA',
    'codigo_plantel': 'OD24061508',
    'direccion': 'URBANIZACIÓN CIUDAD MIRANDA MANZANA 80',
    'telefono': '04129561036',
    'municipio': 'CRISTÓBAL ROJAS',
    'entidad_federal': 'MIRANDA',
    'zona_educativa': 'MIRANDA',
    'localidad': 'CHARALLAVE',
    'plan_estudio': 'EDUCACIÓN MEDIA GENERAL',
    'director_nombre': 'DORCA DIAZ',
    'director_cedula': 'V-18930481',
}

MESES = {
    '1': 'ENERO', '01': 'ENERO', '2': 'FEBRERO', '02': 'FEBRERO',
    '3': 'MARZO', '03': 'MARZO', '4': 'ABRIL', '04': 'ABRIL',
    '5': 'MAYO', '05': 'MAYO', '6': 'JUNIO', '06': 'JUNIO',
    '7': 'JULIO', '07': 'JULIO', '8': 'AGOSTO', '08': 'AGOSTO',
    '9': 'SEPTIEMBRE', '09': 'SEPTIEMBRE', '10': 'OCTUBRE',
    '11': 'NOVIEMBRE', '12': 'DICIEMBRE',
}

# Áreas de formación de la certificación: son EXACTAMENTE las 10 materias
# registradas en el sistema (ver inscripciones/management/commands/setup_materias.py
# y sync_materias.py), escritas en MAYÚSCULAS. Se usan las mismas 10 para los 5
# años porque el sistema registra las 10 materias para 1º–5º.
#
# Los nombres coinciden con los de la base de datos tras normalizar (ver
# _canon_asignatura): sin acentos ni puntuación. Esto garantiza que la nota
# definitiva ('DEF') de cada materia sea DETECTABLE y se rellene automáticamente
# tanto en el PDF como en el Excel.
MATERIAS_SISTEMA = [
    "LENGUA Y LITERATURA",
    "IDIOMAS",
    "MATEMÁTICA",
    "EDUCACIÓN FÍSICA",
    "BIOLOGÍA, AMBIENTE Y TECNOLOGÍA",
    "FÍSICA",
    "QUÍMICA",
    "GEOGRAFÍA, HISTORIA Y SOBERANÍA NACIONAL",
    "INNOVACIÓN TECNOLÓGICA Y PRODUCTIVA",
    "ORIENTACIÓN VOCACIONAL",
]

# Las 10 materias del sistema aplican a los 5 años.
AREAS_POR_ANO = {ano: MATERIAS_SISTEMA for ano in range(1, 6)}

# Sinónimos aceptados para emparejar cada materia de la certificación con los
# nombres de asignatura almacenados en la base de datos. La BD contiene variantes
# y erratas históricas de un mismo ramo (p. ej. "MATEMÁTICAS" vs "MATEMÁTICA",
# "CASTELLANO" vs "LENGUA Y LITERATURA", "GEOGRAFÍA/HISTORIA CIUDADANÍA" vs
# "GEOGRAFÍA, HISTORIA Y SOBERANÍA NACIONAL", "A.C.T", "I.T.P", etc.).
# Se comparan de forma canónica (ver _canon_asignatura): sin acentos ni puntuación.
# Cubrir aquí todas las variantes es lo que hace que la nota sea DETECTABLE
# aunque el docente la haya cargado con otro nombre de asignatura.
_AREA_SINONIMOS = {
    "LENGUA Y LITERATURA": ["LENGUA Y LITERATURA", "CASTELLANO", "LENGUA"],
    "IDIOMAS": ["IDIOMAS", "INGLÉS", "INGLÉS Y OTRAS LENGUAS EXTRANJERAS"],
    "MATEMÁTICA": ["MATEMÁTICA", "MATEMÁTICAS", "MATEMATICAS", "MATEMATICA"],
    "EDUCACIÓN FÍSICA": ["EDUCACIÓN FÍSICA", "EDUACIÓN FÍSICA", "EDUCACION FISICA"],
    "BIOLOGÍA, AMBIENTE Y TECNOLOGÍA": [
        "BIOLOGÍA, AMBIENTE Y TECNOLOGÍA", "BIOLOGÍA",
        "BIOLOGIA, AMBIENTE Y TECNOLOGIA",
        "A.C.T.", "A.C.T", "CIENCIAS NATURALES", "AMBIENTE Y TECNOLOGÍA",
    ],
    "FÍSICA": ["FÍSICA", "FISICA"],
    "QUÍMICA": ["QUÍMICA", "QUIMICA"],
    "GEOGRAFÍA, HISTORIA Y SOBERANÍA NACIONAL": [
        "GEOGRAFÍA, HISTORIA Y SOBERANÍA NACIONAL",
        "GEOGRAFÍA, HISTORIA , Y SOBERANÍA NACIONAL",
        "GEOGRAFÍA, HISTORIA Y CIUDADANÍA",
        "GEOGRAFÍA/HISTORIA CIUDADANÍA",
        "GEOGRAFÍA HISTORIA CIUDADANÍA",
        "GEOGRAFIA HISTORIA CIUDADANIA",
        "GEOGRAFIA, HISTORIA Y SOBERANIA NACIONAL",
    ],
    "INNOVACIÓN TECNOLÓGICA Y PRODUCTIVA": [
        "INNOVACIÓN TECNOLÓGICA Y PRODUCTIVA", "I.T.P.", "I.T.P",
        "INNOVACIÓN TECNOLOGÍA Y PRODUCTIVIDAD",
        "INNOVACION TECNOLOGICA Y PRODUCTIVA",
    ],
    "ORIENTACIÓN VOCACIONAL": ["ORIENTACIÓN VOCACIONAL", "ORIENTACIÓN Y CONVIVENCIA", "ORIENTACION VOCACIONAL"],
}

def convertir_nota_a_letras(nota):
    try:
        n = int(round(float(nota)))
    except (ValueError, TypeError):
        return ""
    
    letras = {
        1: "UNO", 2: "DOS", 3: "TRES", 4: "CUATRO", 5: "CINCO",
        6: "SEIS", 7: "SIETE", 8: "OCHO", 9: "NUEVE", 10: "DIEZ",
        11: "ONCE", 12: "DOCE", 13: "TRECE", 14: "CATORCE", 15: "QUINCE",
        16: "DIECISEIS", 17: "DIECISIETE", 18: "DIECIOCHO", 19: "DIECINUEVE", 20: "VEINTE"
    }
    return letras.get(n, "")

def _canon_asignatura(nombre):
    """
    Normaliza el nombre de una asignatura a una clave canónica para poder
    emparejar las notas de la base de datos con las filas de la plantilla oficial,
    sin depender de acentos, puntuación ni de las variantes/erratas del formato
    (p. ej. "EDUACION FISICA" vs "EDUCACIÓN FÍSICA", o las dos redacciones de
    "INNOVACIÓN TECNOLÓGICA Y PRODUCTIVA").

    Se usa igualdad exacta de la clave canónica (no coincidencia parcial) para
    evitar colisiones como "FISICA" contenida dentro de "EDUCACION FISICA".
    """
    s = unicodedata.normalize('NFKD', str(nombre or '')).encode('ascii', 'ignore').decode('ascii')
    s = re.sub(r'[^A-Za-z0-9 ]', ' ', s).upper()
    s = re.sub(r'\s+', ' ', s).strip()
    s = s.replace('EDUACION', 'EDUCACION')  # errata presente en la plantilla oficial
    if s.startswith('INNOVACION'):           # unifica las dos redacciones del formato
        return 'INNOVACION'
    return s

def _nota_para_area(area_nombre, notas_dict, usados=None):
    """
    Devuelve la nota de la BD que corresponde a un área del nuevo formato,
    probando la propia área y todos sus sinónimos (ver _AREA_SINONIMOS) de forma
    canónica. `usados` (opcional) es un set de claves canónicas ya asignadas en
    ese año, para no repetir una misma nota en dos áreas distintas.
    """
    claves = [area_nombre] + _AREA_SINONIMOS.get(area_nombre, [])
    for clave in claves:
        canon = _canon_asignatura(clave)
        if not canon:
            continue
        if usados is not None and canon in usados:
            continue
        if canon in notas_dict:
            if usados is not None:
                usados.add(canon)
            return notas_dict[canon]
    return None

def _notas_definitivas_por_ano(estudiante, ano_grad):
    """Diccionario {clave canónica -> nota} de las calificaciones 'DEF' de un año."""
    cals = Calificacion.objects.filter(
        inscripcion__estudiante=estudiante,
        inscripcion__ano_grado=ano_grad,
        tipo='DEF',
    )
    return {_canon_asignatura(c.asignatura.nombre): c.nota for c in cals}

def _entero_o_none(nota):
    try:
        return int(round(float(nota))) if nota is not None else None
    except (ValueError, TypeError):
        return None

def _reinyectar_logos(ws, wb):
    """
    Reinserta el logo institucional (Ministerio del Poder Popular para la
    Educación) en el encabezado (recuadro combinado B2:J5 del formato EJEMPLO),
    limpiando primero cualquier imagen o enlace externo residual de la plantilla.

    El alto se calcula a partir de las dimensiones reales de la imagen para
    conservar su proporción y evitar que se deforme si el logo cambia.
    """
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
    from openpyxl.drawing.xdr import XDRPositiveSize2D

    ws._images = []
    wb._external_links = []  # la plantilla trae un enlace externo a otro libro; se descarta

    def _add(nombre, col, col_off, row, row_off, cx):
        ruta = os.path.join(settings.MEDIA_ROOT, nombre)
        if not os.path.exists(ruta):
            return
        img = XLImage(ruta)
        # Mantener la relación de aspecto original de la imagen (cx fija, cy derivada).
        cy = int(cx * img.height / img.width) if img.width else cx
        img.anchor = OneCellAnchor(
            _from=AnchorMarker(col=col, colOff=col_off, row=row, rowOff=row_off),
            ext=XDRPositiveSize2D(cx, cy),
        )
        ws.add_image(img)

    # Ancla en el encabezado: columna B (col=1), fila 2 (row=1), como el original.
    _add('gobierno.png', 1, 171450, 1, 47625, 3800000)

def generar_nota_certificada_automatica(estudiante_id, usuario_nombre):
    """
    Genera el Excel oficial de Notas Certificadas reproduciendo el formato de
    referencia 'EJEMPLO.xlsx' (plantilla limpia 'FORMATO NC EJEMPLO', 10 materias
    del sistema por año) tal cual (bordes, celdas combinadas y logo intactos),
    rellena con la identidad del plantel (Apacuana), los datos del estudiante y
    las calificaciones definitivas ('DEF') de cada año.

    Devuelve una tupla (nota_obj, xlsx_bytes) para poder descargar el archivo
    directamente sin depender del almacenamiento remoto.
    """
    try:
        estudiante = Estudiante.objects.get(cedula_identidad=estudiante_id)
    except Estudiante.DoesNotExist:
        raise Exception(f"No se encontró al estudiante con cédula {estudiante_id}")

    plantilla_path = os.path.join(settings.BASE_DIR, 'FORMATOS EXCEL', PLANTILLA_XLSX)
    if not os.path.exists(plantilla_path):
        raise Exception(f"No se encontró la plantilla oficial '{PLANTILLA_XLSX}'.")

    wb_out = openpyxl.load_workbook(plantilla_path)
    ws_out = wb_out[HOJA_XLSX] if HOJA_XLSX in wb_out.sheetnames else wb_out.active

    # Conservar ambos logos del encabezado y descartar el enlace externo residual.
    _reinyectar_logos(ws_out, wb_out)

    # Ajuste de impresión: una sola página de ancho (Oficio/A4 vertical) y zoom de
    # pantalla cómodo. La plantilla ya trae el diseño del formato EJEMPLO.
    ws_out.page_setup.orientation = 'portrait'
    ws_out.page_setup.fitToWidth = 1
    ws_out.page_setup.fitToHeight = 0
    ws_out.sheet_properties.pageSetUpPr = openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)
    ws_out.print_area = 'B1:V68'
    ws_out.sheet_view.zoomScale = 120

    def _set(coord, valor):
        """Escribe conservando el estilo de la celda (esquina superior si es combinada)."""
        ws_out[coord] = valor

    # ── 1. Encabezado: código y fecha de expedición ──────────────────────────
    # El título (L2) y el plan de estudio (L3) son fijos en la plantilla.
    ahora = datetime.now()
    codigo_generado = f"NC-{ahora.year}-{estudiante.cedula_identidad[-4:]}"
    fecha_larga = f"{ahora.day:02d} DE {MESES.get(str(ahora.month), '').upper()} DE {ahora.year}"
    fecha_nac_str = estudiante.fecha_nacimiento.strftime('%d/%m/%Y') if estudiante.fecha_nacimiento else ''

    _set('S3', f"Código: {codigo_generado}")
    _set('Q4', f"{PLANTEL['localidad']}, {fecha_larga}")

    # ── 2. II. Datos del Plantel que emite (identidad de Apacuana) ────────────
    # Etiquetas fijas en plantilla: "Código Plantel", "Epónimo:", "Dirección",
    # "Teléfono", "Municipio", "Entidad Federal:", "Centro de Desarrollo…".
    _set('D7', PLANTEL['codigo_plantel'])
    _set('K7', PLANTEL['nombre'])
    _set('D8', PLANTEL['direccion'])
    _set('R8', PLANTEL['telefono'])
    _set('D9', PLANTEL['municipio'])
    _set('J9', PLANTEL['entidad_federal'])
    _set('R9', PLANTEL['zona_educativa'])

    # ── 3. III. Datos de identificación del estudiante ───────────────────────
    _set('E11', f"V-{estudiante.cedula_identidad}")
    _set('P11', fecha_nac_str)
    _set('C12', estudiante.apellidos or '')
    _set('O12', estudiante.nombres or '')
    _set('F13', estudiante.pais_nacimiento or 'Venezuela')
    _set('K13', estudiante.estado_nacimiento or '')
    _set('R13', estudiante.municipio_nacimiento or '')

    # ── 4. IV. Planteles donde cursó estudios (nº 1 = Apacuana) ──────────────
    _set('C16', PLANTEL['nombre'])
    _set('G16', PLANTEL['localidad'])
    _set('K16', (PLANTEL['entidad_federal'] or '')[:2])
    # Planteles 2 a 5 (no cursados): Nombre, Localidad y E.F. se marcan con "*".
    #   Izquierda: plantel 2 → fila 17 (C/G/K).
    #   Derecha:   planteles 3, 4 y 5 → filas 15, 16 y 17 (O/R/V).
    for _cel in ('C17', 'G17', 'K17',
                 'O15', 'R15', 'V15',
                 'O16', 'R16', 'V16',
                 'O17', 'R17', 'V17'):
        _set(_cel, '*')

    # ── 5. Fechas de culminación por año (Mes / Año) ─────────────────────────
    fechas_culminacion = {
        1: (estudiante.mes_culminacion_1er_ano, estudiante.ano_culminacion_1er_ano),
        2: (estudiante.mes_culminacion_2do_ano, estudiante.ano_culminacion_2do_ano),
        3: (estudiante.mes_culminacion_3er_ano, estudiante.ano_culminacion_3er_ano),
        4: (estudiante.mes_culminacion_4to_ano, estudiante.ano_culminacion_4to_ano),
        5: (estudiante.mes_culminacion_5to_ano, estudiante.ano_culminacion_5to_ano),
    }

    # ── 6. Plan de estudio: calificaciones por año ───────────────────────────
    # Coordenadas del formato EJEMPLO. 'lado' L = columnas izquierdas, R = derechas.
    COLS = {
        'L': {'area': 2,  'nota': 5,  'letra': 6,  'te': 8,  'mes': 9,  'ano': 10, 'plantel': 11},
        'R': {'area': 14, 'nota': 16, 'letra': 17, 'te': 19, 'mes': 20, 'ano': 21, 'plantel': 22},
    }
    # Cada año ocupa 10 filas (una por materia). 1º izq / 2º der: 22-31;
    # 3º izq / 4º der: 35-44; 5º izq: 48-57. Ver scripts/build_nc_ejemplo_template.py.
    bloques_anos = {
        1: {'lado': 'L', 'row_start': 22, 'row_end': 31},
        2: {'lado': 'R', 'row_start': 22, 'row_end': 31},
        3: {'lado': 'L', 'row_start': 35, 'row_end': 44},
        4: {'lado': 'R', 'row_start': 35, 'row_end': 44},
        5: {'lado': 'L', 'row_start': 48, 'row_end': 57},
    }

    for ano_grad, cfg in bloques_anos.items():
        col = COLS[cfg['lado']]
        notas_dict = _notas_definitivas_por_ano(estudiante, ano_grad)
        mes_val, ano_val = fechas_culminacion.get(ano_grad, ("", ""))
        usados = set()

        for row_idx in range(cfg['row_start'], cfg['row_end'] + 1):
            area_nombre = ws_out.cell(row=row_idx, column=col['area']).value
            if not _canon_asignatura(area_nombre):
                continue  # fila sin área real

            nota = _nota_para_area(area_nombre, notas_dict, usados)
            num = _entero_o_none(nota)

            if num is not None:
                # Materia con nota: se rellena y la columna T-E lleva la marca "F".
                ws_out.cell(row=row_idx, column=col['nota']).value = num
                ws_out.cell(row=row_idx, column=col['letra']).value = convertir_nota_a_letras(num)
                ws_out.cell(row=row_idx, column=col['te']).value = 'F'
                ws_out.cell(row=row_idx, column=col['plantel']).value = 1
                if mes_val:
                    ws_out.cell(row=row_idx, column=col['mes']).value = mes_val
                if ano_val:
                    ws_out.cell(row=row_idx, column=col['ano']).value = ano_val
            else:
                # Materia/año no cursado: cada casilla se marca con un ÚNICO "*".
                for _key in ('nota', 'letra', 'te', 'mes', 'ano', 'plantel'):
                    ws_out.cell(row=row_idx, column=col[_key]).value = '*'

    # ── 7. Firmas: director(a) del plantel (Apacuana) ────────────────────────
    # En el formato EJEMPLO el nombre va en B65 y la cédula en B67.
    _set('B65', PLANTEL['director_nombre'])
    _set('B67', PLANTEL['director_cedula'])

    # ── 8. Serializar a memoria y registrar el expediente ────────────────────
    out_stream = BytesIO()
    wb_out.save(out_stream)
    out_stream.seek(0)
    xlsx_bytes = out_stream.read()

    nombre_archivo = f"NC_Auto_{estudiante.cedula_identidad}_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"

    ya_existe = NotaCertificada.objects.filter(cedula_normalizada=estudiante.cedula_identidad).first()
    nota_obj = ya_existe or NotaCertificada()

    nota_obj.cedula_normalizada = estudiante.cedula_identidad
    nota_obj.nombre_completo = f"{estudiante.apellidos or ''} {estudiante.nombres or ''}".strip()
    nota_obj.nombres = estudiante.nombres or ''
    nota_obj.apellidos = estudiante.apellidos or ''
    nota_obj.cargado_por = f"{usuario_nombre} (Auto XLSX)"
    nota_obj.nombre_archivo_original = nombre_archivo
    nota_obj.save()  # se registra el expediente; el Excel se regenera al vuelo en cada descarga

    return nota_obj, xlsx_bytes

def link_callback(uri, rel):
    """
    Convierte URLs relativas a rutas de sistema absoluto para xhtml2pdf.
    """
    import os
    from django.conf import settings
    # use short circuiting
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

    if not os.path.isfile(path):
        raise Exception('URI no encontrada en el sistema de archivos: %s' % path)
    return path

def generar_nota_certificada_pdf_automatica(estudiante_id, usuario_nombre):
    """
    Genera el archivo PDF automáticamente a partir de los datos en base de datos usando HTML.
    """
    try:
        estudiante = Estudiante.objects.get(cedula_identidad=estudiante_id)
    except Estudiante.DoesNotExist:
        raise Exception(f"No se encontró al estudiante con cédula {estudiante_id}")
        
    ahora = datetime.now()
    codigo_generado = f"NC-{ahora.year}-{estudiante.cedula_identidad[-4:]}"
    fecha_larga = f"{ahora.day:02d} DE {MESES.get(str(ahora.month), '').upper()} DE {ahora.year}"
    fecha_nac_str = estudiante.fecha_nacimiento.strftime('%d/%m/%Y') if estudiante.fecha_nacimiento else ''

    # 1. Fechas de culminación en variables fáciles (Mes / Año)
    fechas_culminacion = {
        1: (estudiante.mes_culminacion_1er_ano, estudiante.ano_culminacion_1er_ano),
        2: (estudiante.mes_culminacion_2do_ano, estudiante.ano_culminacion_2do_ano),
        3: (estudiante.mes_culminacion_3er_ano, estudiante.ano_culminacion_3er_ano),
        4: (estudiante.mes_culminacion_4to_ano, estudiante.ano_culminacion_4to_ano),
        5: (estudiante.mes_culminacion_5to_ano, estudiante.ano_culminacion_5to_ano)
    }

    anos_nombres = {1: "PRIMER", 2: "SEGUNDO", 3: "TERCER", 4: "CUARTO", 5: "QUINTO"}
    anios = []

    for ano_grad in range(1, 6):
        notas_dict = _notas_definitivas_por_ano(estudiante, ano_grad)
        mes_val, ano_val = fechas_culminacion.get(ano_grad, ("", ""))
        usados = set()

        # Filas FIJAS del nuevo formato: una por área de formación del año, en el
        # orden exacto de la plantilla; la nota se rellena por sinónimos si existe.
        filas = []
        for area in AREAS_POR_ANO[ano_grad]:
            num = _entero_o_none(_nota_para_area(area, notas_dict, usados))
            filas.append({
                'area': area,
                'num': num if num is not None else '',
                'letras': convertir_nota_a_letras(num) if num is not None else '',
            })

        anios.append({
            'nombre': anos_nombres[ano_grad],
            'mes': mes_val or '',
            'ano': ano_val or '',
            'filas': filas,
        })

    # Preparar rutas de logos (rutas directas de sistema para xhtml2pdf en Windows)
    def _logo(nombre):
        ruta = os.path.join(settings.MEDIA_ROOT, nombre)
        if not os.path.exists(ruta):
            return None
        return ruta.replace('\\', '/') if os.name == 'nt' else ruta

    context = {
        'plantel': PLANTEL,
        'codigo': codigo_generado,
        'fecha_larga': fecha_larga,
        'telefono': estudiante.telefono_representante or '',
        'e_cedula': estudiante.cedula_identidad,
        'fecha_nacimiento': fecha_nac_str,
        'apellido': estudiante.apellidos or '',
        'nombre': estudiante.nombres or '',
        'lugar_nacimiento': estudiante.lugar_nacimiento or '',
        'estado_nacimiento': estudiante.estado_nacimiento or '',
        'municipio_nacimiento': estudiante.municipio_nacimiento or '',
        'pais_nacimiento': estudiante.pais_nacimiento or 'Venezuela',
        'anios': anios,
        'logo_gobierno': _logo('gobierno.png'),
    }

    html_string = render_to_string('calificaciones/nota_certificada_pdf.html', context)
    
    # Render PDF
    out_stream = BytesIO()
    pisa_status = pisa.CreatePDF(
        html_string, 
        dest=out_stream, 
        link_callback=link_callback
    )
    
    if pisa_status.err:
        raise Exception('Hubo un error al generar el PDF de Notas Certificadas.')
        
    out_stream.seek(0)
    
    # 4. Guardar en memoria y crear registro
    nombre_archivo = f"NC_Auto_{estudiante.cedula_identidad}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    
    ya_existe = NotaCertificada.objects.filter(cedula_normalizada=estudiante.cedula_identidad).first()
    if ya_existe:
        nota_obj = ya_existe
    else:
        nota_obj = NotaCertificada()

    nota_obj.cedula_normalizada = estudiante.cedula_identidad
    nota_obj.nombre_completo = f"{estudiante.apellidos or ''} {estudiante.nombres or ''}".strip()
    nota_obj.nombres = estudiante.nombres or ''
    nota_obj.apellidos = estudiante.apellidos or ''
    nota_obj.cargado_por = f"{usuario_nombre} (Auto PDF)"
    nota_obj.nombre_archivo_original = nombre_archivo
    nota_obj.save() # Guardamos registro pero sin subir archivo a Cloudinary
    
    return nota_obj, out_stream.read()

def procesar_nota_certificada(archivo_subido, usuario_nombre):
    """
    Procesa un archivo .xlsx subido (idealmente como EJEMPLO.xlsx),
    extrae la cédula, busca al estudiante, extrae notas, las guarda,
    y genera el archivo final usando FORMATO.xlsx.
    """
    # 1. Leer archivo en memoria
    archivo_subido.seek(0)
    try:
        wb_in = openpyxl.load_workbook(archivo_subido, data_only=True)
    except Exception as e:
        raise Exception(f"No se pudo leer el archivo Excel. Asegúrate de que sea un formato válido. ({e})")
        
    # Detectar la hoja de forma flexible
    sheet_name = None
    for name in wb_in.sheetnames:
        if name.upper() in ["NCF", "HOJA1", "SHEET1"]:
            sheet_name = name
            break
            
    if not sheet_name:
        # Fallback a la primera hoja
        sheet_name = wb_in.sheetnames[0]
        
    ws_in = wb_in[sheet_name]

    # 2. Extraer Cédula de E11
    cedula_raw = str(ws_in['E11'].value or '')
    cedula = re.sub(r'\D', '', cedula_raw)
    if not cedula or len(cedula) < 6:
        raise Exception(f"No se encontró una cédula válida en la celda E11 del archivo. Valor encontrado: '{cedula_raw}'")

    # 3. Buscar Estudiante
    try:
        estudiante = Estudiante.objects.get(cedula_identidad=cedula)
    except Estudiante.DoesNotExist:
        raise Exception(f"No se encontró al estudiante con cédula {cedula} en la base de datos.")

    # 4. Obtener/Crear Periodo Activo e Inscripción (para guardar calificaciones)
    periodo, _ = PeriodoAcademico.objects.get_or_create(
        activo=True,
        defaults={'nombre': f"{datetime.now().year}-{datetime.now().year+1}", 'fecha_inicio': datetime.now().date(), 'fecha_fin': datetime.now().date()}
    )
    inscripcion, _ = Inscripcion.objects.get_or_create(
        estudiante=estudiante,
        periodo=periodo,
        defaults={'ano_grado': 1, 'seccion': 'A'}
    )

    # 5. Abrir Plantilla FORMATO.xlsx
    plantilla_path = os.path.join(settings.BASE_DIR, 'FORMATOS EXCEL', 'FORMATO.xlsx')
    if not os.path.exists(plantilla_path):
        raise Exception(f"No se encontró la plantilla oficial en {plantilla_path}")

    wb_out = openpyxl.load_workbook(plantilla_path)
    ws_out = wb_out["NCF"]

    # 6. Reemplazar Variables Dinámicas en FORMATO
    codigo_generado = f"NC-{datetime.now().year}-{cedula[-4:]}"
    lugar = "LOS TEQUES" # Default o podría ser de configuración
    fecha_hoy = datetime.now().strftime('%d/%m/%Y')
    
    fecha_nac_str = estudiante.fecha_nacimiento.strftime('%d/%m/%Y') if estudiante.fecha_nacimiento else ''
    
    variables_map = {
        '{{ codigo }}': codigo_generado,
        '{{ lugar }}': lugar,
        '{{ fecha_hoy }}': fecha_hoy,
        '{{ telefono }}': '',
        '{{ e.cedula }}': estudiante.cedula_identidad,
        '{{ fecha_nacimiento }}': fecha_nac_str,
        '{{ apellido }}': estudiante.apellidos or '',
        '{{ nombre }}': estudiante.nombres or '',
        '{{ lugar_nacimiento }}': estudiante.lugar_nacimiento or '',
        '{{ estado_nacimiento }}': estudiante.estado_nacimiento or '',
        '{{ municipio_nacimiento }}': estudiante.municipio_nacimiento or ''
    }

    # Búsqueda y reemplazo de variables
    for row in ws_out.iter_rows():
        for cell in row:
            if isinstance(cell, Cell) and isinstance(cell.value, str) and '{{' in cell.value:
                val = cell.value
                for k, v in variables_map.items():
                    val = val.replace(k, str(v))
                cell.value = val

    # 7. Copiar Calificaciones a Plantilla y Guardar en BD
    # Lado Izquierdo (E a L)
    for row_idx in range(15, 60):
        subj_left = str(ws_in.cell(row=row_idx, column=2).value or '').strip().upper()
        if subj_left in ASIGNATURAS_PREDEFINIDAS:
            nota_val = ws_in.cell(row=row_idx, column=5).value
            
            # Guardar en base de datos si hay nota numérica
            if nota_val is not None and isinstance(nota_val, (int, float)):
                asig = Asignatura.objects.filter(nombre=subj_left).first()
                if not asig:
                    import uuid
                    safe_code = re.sub(r'[^A-Z]', '', subj_left)[:10] + str(uuid.uuid4().hex[:4]).upper()
                    asig = Asignatura.objects.create(nombre=subj_left, codigo=safe_code, ano_grado=1)
                Calificacion.objects.update_or_create(
                    inscripcion=inscripcion, asignatura=asig, tipo='DEF',
                    defaults={'nota': float(nota_val)}
                )

            # Copiar datos a plantilla
            for col_idx in range(5, 13):
                val_in = ws_in.cell(row=row_idx, column=col_idx).value
                cell_out = ws_out.cell(row=row_idx, column=col_idx)
                if isinstance(cell_out, Cell):
                    cell_out.value = val_in

    # Lado Derecho (P a W)
    for row_idx in range(15, 60):
        subj_right = str(ws_in.cell(row=row_idx, column=14).value or '').strip().upper()
        if subj_right in ASIGNATURAS_PREDEFINIDAS:
            nota_val = ws_in.cell(row=row_idx, column=16).value
            
            if nota_val is not None and isinstance(nota_val, (int, float)):
                asig = Asignatura.objects.filter(nombre=subj_right).first()
                if not asig:
                    import uuid
                    safe_code = re.sub(r'[^A-Z]', '', subj_right)[:10] + str(uuid.uuid4().hex[:4]).upper()
                    asig = Asignatura.objects.create(nombre=subj_right, codigo=safe_code, ano_grado=1)
                Calificacion.objects.update_or_create(
                    inscripcion=inscripcion, asignatura=asig, tipo='DEF',
                    defaults={'nota': float(nota_val)}
                )

            for col_idx in range(16, 24):
                val_in = ws_in.cell(row=row_idx, column=col_idx).value
                cell_out = ws_out.cell(row=row_idx, column=col_idx)
                if isinstance(cell_out, Cell):
                    cell_out.value = val_in

    # 8. Guardar en Memoria y crear registro
    out_stream = BytesIO()
    wb_out.save(out_stream)
    out_stream.seek(0)
    
    nombre_archivo = f"NC_{cedula}_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
    
    # 9. Actualizar o crear NotaCertificada
    ya_existe = NotaCertificada.objects.filter(cedula_normalizada=cedula).first()
    if ya_existe:
        ya_existe.archivo_pdf.delete(save=False)
        nota_obj = ya_existe
    else:
        nota_obj = NotaCertificada()

    nota_obj.cedula_normalizada = cedula
    nota_obj.nombre_completo = f"{estudiante.apellidos or ''} {estudiante.nombres or ''}".strip()
    nota_obj.nombres = estudiante.nombres or ''
    nota_obj.apellidos = estudiante.apellidos or ''
    nota_obj.cargado_por = usuario_nombre
    nota_obj.nombre_archivo_original = getattr(archivo_subido, 'name', nombre_archivo)
    nota_obj.save()

    return nota_obj

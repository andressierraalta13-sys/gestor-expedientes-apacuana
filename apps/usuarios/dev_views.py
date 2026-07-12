"""
Panel de Observabilidad Profesional — Developer Console
========================================================
Endpoints para el panel avanzado del desarrollador con:
  - Métricas históricas en tiempo real (CPU, RAM, requests, latencia)
  - Streaming de logs vía polling (buffer circular en memoria)
  - Detección automática de anomalías
  - Auditoría técnica avanzada con persistencia en BD
  - Herramientas de mantenimiento (DB backup/restore, SQL, cache)
"""
import os
import sys
import csv
import json
import time
import psutil
import logging
import platform
import shutil
import datetime
import collections
from functools import wraps

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.core.cache import cache
from django.conf import settings
from django.db import connection
from django.utils import timezone

from auditoria.models import registrar_evento, EventoAuditoria, registrar_dev_audit, DevAuditoriaLog, Notificacion
# ── Log Buffer Circular ───────────────────────────────────────────────────────
# Buffer en memoria de las últimas 500 líneas de log de la aplicación
LOG_BUFFER = collections.deque(maxlen=500)

class DevLogHandler(logging.Handler):
    """Handler que intercepta todos los logs de Django y los almacena en el buffer."""
    def emit(self, record):
        try:
            msg = self.format(record)
            LOG_BUFFER.appendleft({
                'ts':    record.created,
                'level': record.levelname,
                'name':  record.name,
                'msg':   msg,
            })
        except Exception:
            pass

# Registrar el handler en el logger raíz (solo una vez)
_dev_handler = DevLogHandler()
_dev_handler.setFormatter(logging.Formatter('[%(name)s] %(message)s'))
_dev_handler.setLevel(logging.DEBUG)

_root_logger = logging.getLogger()
if not any(isinstance(h, DevLogHandler) for h in _root_logger.handlers):
    _root_logger.addHandler(_dev_handler)
    if _root_logger.level == logging.NOTSET or _root_logger.level > logging.DEBUG:
        _root_logger.setLevel(logging.DEBUG)

# ── Constantes de Telemetría ──────────────────────────────────────────────────
_TELEMETRY_BUCKET_KEY  = 'dev_telemetry_bucket:{}'
_TELEMETRY_INDEX_KEY   = 'dev_telemetry_index'
_TELEMETRY_WINDOW_MINS = 60

# ── Decorator de protección ────────────────────────────────────────────────────
def desarrollador_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.rol != 'DESARROLLADOR':
            raise PermissionDenied("Acceso restringido únicamente para Desarrollador.")
        return view_func(request, *args, **kwargs)
    return _wrapped


# ── Utilidades internas ────────────────────────────────────────────────────────
def _get_client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '?')


def _collect_telemetry_window():
    """Recolecta todos los buckets de telemetría activos en la ventana."""
    index = cache.get(_TELEMETRY_INDEX_KEY, [])
    all_entries = []
    for bucket in index:
        entries = cache.get(_TELEMETRY_BUCKET_KEY.format(bucket), [])
        all_entries.extend(entries)
    return all_entries


def _compute_metrics_series(entries, window_minutes=60):
    """
    Agrupa entries por minuto y calcula métricas para series de Chart.js.
    Devuelve listas alineadas: labels, cpu_series, ram_series, req_series, err_series, lat_series
    """
    from datetime import datetime as dt, timedelta
    now_ts  = timezone.now().timestamp()
    cutoff  = now_ts - window_minutes * 60

    # Filtrar a ventana
    entries = [e for e in entries if e.get('ts', 0) >= cutoff]

    # Agrupar por minuto
    buckets = {}
    for e in entries:
        minute = int(e['ts'] // 60) * 60  # epoch redondeado al minuto
        if minute not in buckets:
            buckets[minute] = {'count': 0, 'errors': 0, 'lat_sum': 0.0}
        buckets[minute]['count']   += 1
        if e.get('status', 200) >= 500:
            buckets[minute]['errors'] += 1
        buckets[minute]['lat_sum'] += e.get('latencia_ms', 0)

    # Generar serie de los últimos N minutos
    series_labels = []
    req_series    = []
    err_series    = []
    lat_series    = []

    for i in range(window_minutes - 1, -1, -1):
        minute_ts = int((now_ts - i * 60) // 60) * 60
        label     = dt.fromtimestamp(minute_ts).strftime('%H:%M')
        bucket    = buckets.get(minute_ts, {'count': 0, 'errors': 0, 'lat_sum': 0.0})
        series_labels.append(label)
        req_series.append(bucket['count'])
        err_series.append(bucket['errors'])
        lat_avg = round(bucket['lat_sum'] / bucket['count'], 1) if bucket['count'] > 0 else 0
        lat_series.append(lat_avg)

    return series_labels, req_series, err_series, lat_series


# ═══════════════════════════════════════════════════════════════════════════════
# VISTA PRINCIPAL — Panel de Desarrollador
# ═══════════════════════════════════════════════════════════════════════════════

@desarrollador_required
def dev_panel_view(request):
    """Panel principal del desarrollador — consola de observabilidad."""
    process  = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    vm       = psutil.virtual_memory()

    system_info = {
        'os':             platform.system(),
        'os_release':     platform.release(),
        'python_version': platform.python_version(),
        'ram_proceso_mb': f"{mem_info.rss / 1024 / 1024:.1f}",
        'ram_sistema_pct': vm.percent,
        'ram_sistema_mb': f"{vm.used / 1024 / 1024:.0f}",
        'ram_total_mb':   f"{vm.total / 1024 / 1024:.0f}",
        'cpu_percent':    psutil.cpu_percent(interval=0.1),
        'cpu_count':      psutil.cpu_count(),
        'db_engine':      settings.DATABASES['default']['ENGINE'].split('.')[-1].upper(),
        'django_version': __import__('django').VERSION,
    }

    # Registrar visita en auditoría técnica
    registrar_dev_audit(
        accion='VIEW_PANEL',
        usuario=request.user.username,
        ip_address=_get_client_ip(request),
        descripcion='Acceso al Panel de Observabilidad',
        nivel_riesgo='INFORMATIVO',
    )

    return render(request, 'usuarios/dev_panel.html', {'system_info': system_info})


# ═══════════════════════════════════════════════════════════════════════════════
# APIs DE MÉTRICAS
# ═══════════════════════════════════════════════════════════════════════════════

@desarrollador_required
@require_GET
def dev_metricas_view(request):
    """API: Métricas del sistema en tiempo real + series históricas."""
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    vm = psutil.virtual_memory()

    # Métricas instantáneas
    cpu_now    = psutil.cpu_percent(interval=0.1)
    ram_proc   = round(mem_info.rss / 1024 / 1024, 1)
    ram_sys    = vm.percent
    ram_mb     = round(vm.used / 1024 / 1024)
    ram_total  = round(vm.total / 1024 / 1024)

    # Series históricas desde telemetría
    entries = _collect_telemetry_window()
    labels, req_series, err_series, lat_series = _compute_metrics_series(entries, 60)

    # Totales del último minuto
    now_ts  = timezone.now().timestamp()
    last_min = [e for e in entries if e.get('ts', 0) >= now_ts - 60]
    req_min  = len(last_min)
    err_min  = sum(1 for e in last_min if e.get('status', 200) >= 500)
    lat_avg  = round(sum(e.get('latencia_ms', 0) for e in last_min) / max(len(last_min), 1), 1)

    # Snapshots CPU últimos 60 puntos (desde cache si existen)
    cpu_history = cache.get('dev_cpu_history', [])
    ram_history = cache.get('dev_ram_history', [])

    # Guardar snapshot actual
    cpu_history.append(round(cpu_now, 1))
    ram_history.append(ram_proc)
    if len(cpu_history) > 60:
        cpu_history = cpu_history[-60:]
        ram_history = ram_history[-60:]
    cache.set('dev_cpu_history', cpu_history, timeout=3700)
    cache.set('dev_ram_history', ram_history, timeout=3700)

    # Conexiones DB activas (para SQLite siempre 1)
    try:
        with connection.cursor() as c:
            if 'sqlite' in settings.DATABASES['default']['ENGINE']:
                db_connections = 1
            else:
                c.execute("SELECT count(*) FROM pg_stat_activity WHERE state='active'")
                db_connections = c.fetchone()[0]
    except Exception:
        db_connections = '?'

    return JsonResponse({
        'ok': True,
        'snapshot': {
            'cpu_pct':        cpu_now,
            'ram_proceso_mb': ram_proc,
            'ram_sistema_pct': ram_sys,
            'ram_mb':         ram_mb,
            'ram_total_mb':   ram_total,
            'req_ultimo_min': req_min,
            'err_ultimo_min': err_min,
            'latencia_avg_ms': lat_avg,
            'db_connections': db_connections,
        },
        'series': {
            'labels':     labels,
            'cpu':        cpu_history[-len(labels):] if len(cpu_history) >= len(labels) else cpu_history,
            'ram':        ram_history[-len(labels):] if len(ram_history) >= len(labels) else ram_history,
            'requests':   req_series,
            'errores':    err_series,
            'latencia':   lat_series,
        }
    })


# ═══════════════════════════════════════════════════════════════════════════════
# API DE LOGS EN VIVO
# ═══════════════════════════════════════════════════════════════════════════════

@desarrollador_required
@require_GET
def dev_logs_view(request):
    """
    API de logs en vivo via polling.
    Parámetros:
      ?since=<epoch_float>  → solo logs más recientes que ese timestamp
      ?level=<LEVEL>        → filtrar por nivel (ERROR, WARNING, INFO, etc.)
      ?q=<texto>            → buscar texto en el mensaje
      ?limit=<int>          → máximo de entradas (default 100)
    """
    since = float(request.GET.get('since', 0))
    level = request.GET.get('level', '').upper()
    q     = request.GET.get('q', '').lower()
    limit = min(int(request.GET.get('limit', 100)), 500)

    logs = list(LOG_BUFFER)  # más recientes primero

    # Filtros
    if since:
        logs = [l for l in logs if l.get('ts', 0) > since]
    if level:
        logs = [l for l in logs if l.get('level', '') == level]
    if q:
        logs = [l for l in logs if q in l.get('msg', '').lower()]

    logs = logs[:limit]

    # Calcular nuevo cursor
    newest_ts = logs[0]['ts'] if logs else since

    return JsonResponse({
        'ok':       True,
        'logs':     logs,
        'cursor':   newest_ts,
        'total':    len(list(LOG_BUFFER)),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# API DE ANOMALÍAS
# ═══════════════════════════════════════════════════════════════════════════════

@desarrollador_required
@require_GET
def dev_anomalias_view(request):
    """Detecta y devuelve anomalías activas del sistema."""
    anomalias = []

    # 1. RAM del proceso
    process = psutil.Process(os.getpid())
    ram_proc_mb = process.memory_info().rss / 1024 / 1024

    # 2. RAM del sistema
    vm = psutil.virtual_memory()
    if vm.percent >= 85:
        sev = 'CRITICO' if vm.percent >= 95 else 'ADVERTENCIA'
        anomalias.append({
            'tipo':        'RAM_ALTA',
            'severidad':   sev,
            'titulo':      f'RAM del Sistema al {vm.percent:.1f}%',
            'descripcion': f'Uso de memoria: {vm.used//1024//1024} MB / {vm.total//1024//1024} MB',
            'valor':       vm.percent,
            'umbral':      85,
        })

    # 3. CPU sostenida
    cpu = psutil.cpu_percent(interval=0.3)
    if cpu >= 85:
        sev = 'CRITICO' if cpu >= 95 else 'ADVERTENCIA'
        anomalias.append({
            'tipo':        'CPU_ALTA',
            'severidad':   sev,
            'titulo':      f'CPU al {cpu:.1f}%',
            'descripcion': f'Carga de CPU superior al umbral de alerta (85%)',
            'valor':       cpu,
            'umbral':      85,
        })

    # 4. Errores 500 en último minuto
    entries = _collect_telemetry_window()
    now_ts  = timezone.now().timestamp()
    last_min = [e for e in entries if e.get('ts', 0) >= now_ts - 60]
    err_min  = sum(1 for e in last_min if e.get('status', 200) >= 500)
    if err_min >= 3:
        sev = 'CRITICO' if err_min >= 10 else 'ADVERTENCIA'
        anomalias.append({
            'tipo':        'ERRORES_500',
            'severidad':   sev,
            'titulo':      f'{err_min} errores HTTP 500 en el último minuto',
            'descripcion': 'El servidor está generando errores internos de forma frecuente.',
            'valor':       err_min,
            'umbral':      3,
        })

    # 5. Latencia alta
    if last_min:
        lat_avg = sum(e.get('latencia_ms', 0) for e in last_min) / len(last_min)
        if lat_avg >= 1500:
            sev = 'CRITICO' if lat_avg >= 5000 else 'ADVERTENCIA'
            anomalias.append({
                'tipo':        'LATENCIA_ALTA',
                'severidad':   sev,
                'titulo':      f'Latencia promedio: {lat_avg:.0f}ms',
                'descripcion': 'El tiempo de respuesta supera el umbral de 1500ms.',
                'valor':       round(lat_avg),
                'umbral':      1500,
            })

    # 6. Requests por minuto muy bajos (posible caída)
    req_min = len(last_min)
    total_entries = len(entries)

    return JsonResponse({
        'ok':        True,
        'anomalias': anomalias,
        'total':     len(anomalias),
        'stats': {
            'cpu':      cpu,
            'ram_pct':  vm.percent,
            'err_min':  err_min,
            'req_min':  req_min,
        }
    })


# ═══════════════════════════════════════════════════════════════════════════════
# API DE AUDITORÍA TÉCNICA
# ═══════════════════════════════════════════════════════════════════════════════

@desarrollador_required
@require_GET
def dev_auditoria_api_view(request):
    """API paginada de logs de auditoría técnica del desarrollador."""
    qs = DevAuditoriaLog.objects.all()

    # Filtros
    accion   = request.GET.get('accion', '')
    usuario  = request.GET.get('usuario', '')
    riesgo   = request.GET.get('riesgo', '')
    q        = request.GET.get('q', '')
    fecha_desde = request.GET.get('desde', '')
    fecha_hasta = request.GET.get('hasta', '')

    if accion:
        qs = qs.filter(accion=accion)
    if usuario:
        qs = qs.filter(usuario__icontains=usuario)
    if riesgo:
        qs = qs.filter(nivel_riesgo=riesgo)
    if q:
        from django.db.models import Q as DQ
        qs = qs.filter(DQ(descripcion__icontains=q) | DQ(query_sql__icontains=q))
    if fecha_desde:
        try:
            qs = qs.filter(timestamp__date__gte=fecha_desde)
        except Exception:
            pass
    if fecha_hasta:
        try:
            qs = qs.filter(timestamp__date__lte=fecha_hasta)
        except Exception:
            pass

    # Paginación
    page     = max(int(request.GET.get('page', 1)), 1)
    per_page = min(int(request.GET.get('per_page', 25)), 100)
    total    = qs.count()
    offset   = (page - 1) * per_page
    logs     = qs[offset:offset + per_page]

    data = []
    for log in logs:
        data.append({
            'id':           log.id,
            'accion':       log.accion,
            'accion_label': log.get_accion_display(),
            'usuario':      log.usuario,
            'ip':           str(log.ip_address or '—'),
            'timestamp':    log.timestamp.strftime('%d/%m/%Y %I:%M:%S %p'),
            'timestamp_iso': log.timestamp.isoformat(),
            'nivel_riesgo': log.nivel_riesgo,
            'descripcion':  log.descripcion[:200],
            'query_sql':    log.query_sql[:300] if log.query_sql else '',
            'rows_affected': log.rows_affected,
            'execution_ms': log.execution_ms,
            'exitoso':      log.exitoso,
        })

    return JsonResponse({
        'ok':       True,
        'data':     data,
        'total':    total,
        'page':     page,
        'per_page': per_page,
        'pages':    max(1, (total + per_page - 1) // per_page),
    })


@desarrollador_required
@require_GET
def dev_auditoria_export_view(request):
    """Exporta la auditoría técnica en CSV o JSON."""
    fmt = request.GET.get('format', 'csv').lower()
    qs  = DevAuditoriaLog.objects.all().order_by('-timestamp')[:5000]

    registrar_dev_audit(
        accion='EXPORT_AUDIT',
        usuario=request.user.username,
        ip_address=_get_client_ip(request),
        descripcion=f'Exportación de auditoría técnica en formato {fmt.upper()}',
        nivel_riesgo='ADVERTENCIA',
    )

    if fmt == 'json':
        data = list(qs.values(
            'id', 'accion', 'usuario', 'ip_address', 'timestamp',
            'nivel_riesgo', 'descripcion', 'query_sql', 'rows_affected',
            'execution_ms', 'exitoso'
        ))
        # Serializar datetimes
        for row in data:
            row['timestamp'] = row['timestamp'].isoformat()
            if row['ip_address'] is None:
                row['ip_address'] = ''
        resp = HttpResponse(
            json.dumps(data, ensure_ascii=False, indent=2),
            content_type='application/json'
        )
        resp['Content-Disposition'] = f'attachment; filename="dev_audit_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.json"'
        return resp

    # CSV por defecto
    resp = HttpResponse(content_type='text/csv; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="dev_audit_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    resp.write('\ufeff')  # BOM para Excel

    writer = csv.writer(resp)
    writer.writerow(['ID', 'Acción', 'Usuario', 'IP', 'Timestamp', 'Riesgo',
                     'Descripción', 'Query SQL', 'Filas', 'Tiempo (ms)', 'Exitoso'])
    for log in qs:
        writer.writerow([
            log.id,
            log.get_accion_display(),
            log.usuario,
            str(log.ip_address or ''),
            log.timestamp.strftime('%d/%m/%Y %I:%M:%S %p'),
            log.nivel_riesgo,
            log.descripcion,
            log.query_sql,
            log.rows_affected or '',
            log.execution_ms or '',
            'Sí' if log.exitoso else 'No',
        ])
    return resp


@desarrollador_required
@require_GET
def dev_logs_download_view(request):
    """Descarga el contenido actual del buffer de logs como archivo .log."""
    registrar_dev_audit(
        accion='EXPORT_LOGS',
        usuario=request.user.username,
        ip_address=_get_client_ip(request),
        descripcion='Descarga del buffer de logs en vivo',
        nivel_riesgo='INFORMATIVO',
    )
    logs   = list(LOG_BUFFER)
    lines  = []
    for l in reversed(logs):
        ts_str = datetime.datetime.fromtimestamp(l['ts']).strftime('%Y-%m-%d %I:%M:%S %p')
        lines.append(f"[{ts_str}] [{l['level']}] {l['name']} — {l['msg']}")
    content = '\n'.join(lines)
    resp = HttpResponse(content, content_type='text/plain; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="app_logs_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.log"'
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# HERRAMIENTAS DE MANTENIMIENTO (existentes, mejoradas con audit técnica)
# ═══════════════════════════════════════════════════════════════════════════════

@desarrollador_required
def dev_export_db_view(request):
    """Descarga el archivo db.sqlite3 directamente."""
    if 'sqlite' not in settings.DATABASES['default']['ENGINE'].lower():
        return JsonResponse({'error': 'La exportación directa solo está soportada para SQLite.'}, status=400)

    db_path = settings.DATABASES['default']['NAME']
    if not os.path.exists(db_path):
        return JsonResponse({'error': 'Archivo de base de datos no encontrado.'}, status=404)

    db_size = os.path.getsize(db_path)

    with open(db_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/x-sqlite3')
        fname = f'backup_gestor_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.sqlite3'
        response['Content-Disposition'] = f'attachment; filename="{fname}"'

    registrar_evento('EXPORT_DB', 'Exportación completa de base de datos', 'Sistema', request.user.username, 'CRITICO')
    registrar_dev_audit(
        accion='EXPORT_DB',
        usuario=request.user.username,
        ip_address=_get_client_ip(request),
        descripcion=f'Exportación de BD — {fname} ({db_size:,} bytes)',
        nivel_riesgo='CRITICO',
        payload_json={'filename': fname, 'size_bytes': db_size},
    )
    return response


@desarrollador_required
@csrf_exempt
@require_POST
def dev_restore_db_view(request):
    """Restaura la base de datos reemplazando el archivo db.sqlite3."""
    if 'sqlite' not in settings.DATABASES['default']['ENGINE'].lower():
        return JsonResponse({'error': 'La restauración directa solo está soportada para SQLite.'}, status=400)

    if 'db_file' not in request.FILES:
        return JsonResponse({'error': 'No se proporcionó archivo de base de datos.'}, status=400)

    uploaded_file = request.FILES['db_file']
    if not uploaded_file.name.endswith('.sqlite3'):
        return JsonResponse({'error': 'El archivo debe tener extensión .sqlite3'}, status=400)

    db_path    = settings.DATABASES['default']['NAME']
    backup_path = f"{db_path}.backup_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

    t0 = time.monotonic()
    try:
        if os.path.exists(db_path):
            shutil.copy2(db_path, backup_path)
        with open(db_path, 'wb+') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)
        ms = round((time.monotonic() - t0) * 1000, 1)
        registrar_evento('RESTORE_DB', 'Restauración completa de base de datos', 'Sistema', request.user.username, 'CRITICO')
        registrar_dev_audit(
            accion='RESTORE_DB',
            usuario=request.user.username,
            ip_address=_get_client_ip(request),
            descripcion=f'Restauración de BD desde {uploaded_file.name}',
            execution_ms=ms,
            nivel_riesgo='CRITICO',
        )
        return JsonResponse({'ok': True, 'mensaje': 'Base de datos restaurada correctamente. Se creó un backup automático.'})
    except Exception as e:
        registrar_dev_audit(
            accion='RESTORE_DB',
            usuario=request.user.username,
            ip_address=_get_client_ip(request),
            descripcion=f'Error al restaurar BD: {e}',
            nivel_riesgo='CRITICO',
            exitoso=False,
        )
        return JsonResponse({'error': f'Error al restaurar: {str(e)}'}, status=500)


@desarrollador_required
@csrf_exempt
@require_POST
def dev_run_sql_view(request):
    """Ejecuta consultas SQL en crudo con auditoría completa."""
    try:
        data  = json.loads(request.body)
        query = data.get('query', '').strip()
    except Exception:
        return JsonResponse({'error': 'JSON inválido.'}, status=400)

    if not query:
        return JsonResponse({'error': 'La consulta SQL está vacía.'}, status=400)

    is_select = query.lower().lstrip().startswith(('select', 'pragma'))
    accion_tipo = 'SQL_EXECUTE' if is_select else 'SQL_MODIFY'
    nivel_riesgo = 'ADVERTENCIA' if is_select else 'CRITICO'

    t0 = time.monotonic()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query)
            ms = round((time.monotonic() - t0) * 1000, 2)

            if is_select:
                columns      = [col[0] for col in cursor.description] if cursor.description else []
                rows         = [list(r) for r in cursor.fetchall()]
                rows_count   = len(rows)
                # Serializar datetimes/fechas
                import datetime as _dt
                for row in rows:
                    for i, v in enumerate(row):
                        if isinstance(v, (_dt.datetime, _dt.date)):
                            row[i] = str(v)
                registrar_dev_audit(
                    accion=accion_tipo,
                    usuario=request.user.username,
                    ip_address=_get_client_ip(request),
                    descripcion=f'SELECT ejecutado: {query[:100]}',
                    query_sql=query,
                    rows_affected=rows_count,
                    execution_ms=ms,
                    nivel_riesgo=nivel_riesgo,
                )
                registrar_evento('SQL_RAW', f'SQL: {query[:80]}', 'Sistema', request.user.username, 'CRITICO')
                return JsonResponse({'ok': True, 'columns': columns, 'rows': rows, 'execution_ms': ms, 'rows_count': rows_count})
            else:
                rows_affected = cursor.rowcount
                connection.commit() if hasattr(connection, 'commit') else None
                registrar_dev_audit(
                    accion=accion_tipo,
                    usuario=request.user.username,
                    ip_address=_get_client_ip(request),
                    descripcion=f'Modificación SQL: {query[:100]}',
                    query_sql=query,
                    rows_affected=rows_affected,
                    execution_ms=ms,
                    nivel_riesgo=nivel_riesgo,
                )
                registrar_evento('SQL_RAW_MODIFICACION', f'SQL Modificador: {query}', 'Sistema', request.user.username, 'CRITICO')
                return JsonResponse({'ok': True, 'mensaje': f'Consulta ejecutada. Filas afectadas: {rows_affected}', 'execution_ms': ms, 'rows_affected': rows_affected})
    except Exception as e:
        ms = round((time.monotonic() - t0) * 1000, 2)
        registrar_dev_audit(
            accion=accion_tipo,
            usuario=request.user.username,
            ip_address=_get_client_ip(request),
            descripcion=f'Error SQL: {str(e)[:200]}',
            query_sql=query,
            execution_ms=ms,
            nivel_riesgo='CRITICO',
            exitoso=False,
        )
        return JsonResponse({'error': str(e)}, status=400)


@desarrollador_required
@csrf_exempt
@require_POST
def dev_clear_cache_view(request):
    """Limpia la caché global del sistema."""
    t0 = time.monotonic()
    cache.clear()
    ms = round((time.monotonic() - t0) * 1000, 2)
    registrar_evento('CLEAR_CACHE', 'Caché global purgada', 'Sistema', request.user.username, 'INFORMATIVO')
    registrar_dev_audit(
        accion='CLEAR_CACHE',
        usuario=request.user.username,
        ip_address=_get_client_ip(request),
        descripcion='Caché global del sistema purgada',
        execution_ms=ms,
        nivel_riesgo='ADVERTENCIA',
    )
    return JsonResponse({'ok': True, 'mensaje': f'Caché purgada correctamente en {ms}ms.'})


@desarrollador_required
@csrf_exempt
@require_POST
def dev_purge_audit_view(request):
    """Elimina eventos de auditoría no críticos."""
    t0 = time.monotonic()
    eliminados, _ = EventoAuditoria.objects.exclude(nivel_riesgo='CRITICO').delete()
    ms = round((time.monotonic() - t0) * 1000, 2)
    registrar_evento('PURGE_AUDIT', f'Purga de {eliminados} registros de auditoría no críticos', 'Sistema', request.user.username, 'CRITICO')
    registrar_dev_audit(
        accion='PURGE_AUDIT',
        usuario=request.user.username,
        ip_address=_get_client_ip(request),
        descripcion=f'Purga de {eliminados} eventos de auditoría no críticos',
        rows_affected=eliminados,
        execution_ms=ms,
        nivel_riesgo='CRITICO',
    )
    return JsonResponse({'ok': True, 'mensaje': f'Se eliminaron {eliminados} registros de auditoría en {ms}ms.'})


@desarrollador_required
@csrf_exempt
@require_POST
def dev_test_error_view(request):
    """Levanta un error a propósito para testear manejadores 500."""
    registrar_evento('TEST_ERROR', 'Simulación de excepción 500', 'Sistema', request.user.username, 'ADVERTENCIA')
    registrar_dev_audit(
        accion='TEST_ERROR',
        usuario=request.user.username,
        ip_address=_get_client_ip(request),
        descripcion='Test de excepción 500 lanzado intencionalmente',
        nivel_riesgo='ADVERTENCIA',
    )
    raise Exception("Esta es una excepción de prueba lanzada intencionalmente por el desarrollador.")


# ═══════════════════════════════════════════════════════════════════════════════
# NUEVAS HERRAMIENTAS AVANZADAS DE BASE DE DATOS (DBA)
# ═══════════════════════════════════════════════════════════════════════════════

@desarrollador_required
@require_GET
def dev_db_status_view(request):
    """Obtiene el estado avanzado de la base de datos PostgreSQL/Supabase."""
    is_sqlite = 'sqlite' in settings.DATABASES['default']['ENGINE'].lower()
    
    db_status = {
        'engine': settings.DATABASES['default']['ENGINE'].split('.')[-1].upper(),
        'size': 'N/A',
        'connections': 1 if is_sqlite else 0,
        'version': 'SQLite' if is_sqlite else 'PostgreSQL',
    }

    if not is_sqlite:
        try:
            with connection.cursor() as c:
                # Versión
                c.execute("SELECT version();")
                db_status['version'] = c.fetchone()[0].split(',')[0]
                
                # Tamaño de la BD
                c.execute("SELECT pg_database_size(current_database());")
                size_bytes = c.fetchone()[0]
                db_status['size'] = f"{size_bytes / 1024 / 1024:.2f} MB"
                
                # Conexiones
                c.execute("SELECT count(*) FROM pg_stat_activity;")
                db_status['connections'] = c.fetchone()[0]
        except Exception as e:
            db_status['error'] = str(e)

    return JsonResponse({'ok': True, 'status': db_status})



@desarrollador_required
@csrf_exempt
@require_POST
def dev_db_optimize_view(request):
    """Optimiza la base de datos limpiando sesiones expiradas y caché inactiva."""
    from django.contrib.sessions.models import Session
    from django.utils import timezone
    
    t0 = time.monotonic()
    try:
        # 1. Limpiar sesiones expiradas
        eliminados, _ = Session.objects.filter(expire_date__lt=timezone.now()).delete()
        
        # 2. Purgar caché global para liberar memoria (opcional)
        cache.clear()
        
        # 3. VACUUM en PostgreSQL (no se puede en bloque de transacción normal de Django fácilmente)
        # Lo omitimos para evitar errores de transacciones.
        
        ms = round((time.monotonic() - t0) * 1000, 2)
        
        registrar_dev_audit(
            accion='SQL_MODIFY',
            usuario=request.user.username,
            ip_address=_get_client_ip(request),
            descripcion=f'Optimización de BD: {eliminados} sesiones expiradas eliminadas, caché purgada.',
            nivel_riesgo='ADVERTENCIA',
            execution_ms=ms,
        )
        
        return JsonResponse({'ok': True, 'mensaje': f'Mantenimiento exitoso. Se limpiaron {eliminados} sesiones expiradas en {ms}ms.'})
    except Exception as e:
        return JsonResponse({'error': f'Error en mantenimiento: {str(e)}'}, status=500)


@desarrollador_required
@csrf_exempt
@require_POST
def dev_db_close_connections_view(request):
    """Cierra conexiones inactivas (Solo PostgreSQL)."""
    is_sqlite = 'sqlite' in settings.DATABASES['default']['ENGINE'].lower()
    if is_sqlite:
        return JsonResponse({'error': 'No soportado en SQLite.'}, status=400)
        
    t0 = time.monotonic()
    try:
        with connection.cursor() as c:
            # Terminar conexiones inactivas
            c.execute("""
                SELECT count(pg_terminate_backend(pid)) 
                FROM pg_stat_activity 
                WHERE state = 'idle' AND pid <> pg_backend_pid();
            """)
            cerradas = c.fetchone()[0]
            
        ms = round((time.monotonic() - t0) * 1000, 2)
        
        registrar_dev_audit(
            accion='SQL_MODIFY',
            usuario=request.user.username,
            ip_address=_get_client_ip(request),
            descripcion=f'Limpieza de conexiones DB: {cerradas} conexiones inactivas terminadas.',
            nivel_riesgo='CRITICO',
            execution_ms=ms,
        )
        
        return JsonResponse({'ok': True, 'mensaje': f'Se terminaron {cerradas} conexiones inactivas de Supabase en {ms}ms.'})
    except Exception as e:
        return JsonResponse({'error': f'Error al limpiar conexiones: {str(e)}'}, status=500)

@login_required
@desarrollador_required
def enviar_notificacion_dev_view(request):
    """
    Vista para que el desarrollador envíe notificaciones globales (Actualizaciones, Avisos de Sistema).
    """
    from django.contrib import messages
    if request.method == 'POST':
        tipo = request.POST.get('tipo', 'ACTUALIZACION')
        titulo = request.POST.get('titulo', '').strip()
        mensaje = request.POST.get('mensaje', '').strip()

        if not titulo or not mensaje:
            messages.error(request, 'El título y el mensaje son obligatorios.')
        else:
            try:
                # Al omitir usuario_destino, la notificación es global
                Notificacion.objects.create(
                    tipo=tipo,
                    titulo=titulo,
                    mensaje=mensaje,
                    usuario_destino=None
                )
                registrar_dev_audit(
                    accion='OTHER',
                    usuario=request.user.username,
                    ip_address=_get_client_ip(request),
                    descripcion=f'Notificación Global Enviada: [{tipo}] {titulo}',
                    nivel_riesgo='INFORMATIVO',
                )
                messages.success(request, 'Notificación global distribuida con éxito.')
                return redirect('dev_panel')
            except Exception as e:
                messages.error(request, f'Error al enviar notificación: {e}')

    return render(request, 'dev/enviar_notificacion.html')

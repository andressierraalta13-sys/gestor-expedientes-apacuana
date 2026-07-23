from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views import (dashboard_view, expedientes_view,
                    titulos_view, auditoria_view, ia_riesgos_view, auditoria_limpiar_view,
                    nuevo_expediente_view, api_buscar_expedientes, api_check_estudiante,
                    lista_solventes_view, lista_incompletos_view,
                    detalle_expediente_view, editar_expediente_view, eliminar_expediente_view,
                    eliminar_masivo_expedientes_view,
                    digitalizacion_masiva_view, generar_titulo_view, generar_constancia_estudio_view,
                    emitir_documento_formato_view, generar_boleta_view,
                    guardar_observacion_view, listar_observaciones_view, pdf_observacion_view,
                    eliminar_observacion_view, notificar_representante_view,
                    api_subir_foto_estudiante,
                    notas_docentes_view, actas_consejos_view, actas_compromisos_view, actas_inasistencias_view,
                    api_editar_calificacion_view, api_eliminar_calificaciones_ano_view)
from calificaciones.views import (
    carga_masiva_view, notas_certificadas_view,
    notas_certificadas_upload_view, notas_certificadas_download_view,
    notas_certificadas_unificar_view, notas_certificadas_delete_view,
    emitir_notas_certificadas_auto_view, emitir_notas_certificadas_xlsx_view
)
from calificaciones.notas_views import notas_calificaciones_view
from ia_analitica.asistente_view import asistente_chat_view
from auditoria.views import centro_notificaciones_view
from usuarios.views import login_view, custom_logout_view, crear_operador_view, revocar_operador_view, usuarios_view, expediente_usuario_view, guardar_perfil_usuario_view, eliminar_usuario_view
from usuarios.dev_views import (
    dev_panel_view, dev_export_db_view, dev_restore_db_view, dev_run_sql_view,
    dev_clear_cache_view, dev_purge_audit_view, dev_test_error_view,
    # Nuevas vistas de observabilidad
    dev_metricas_view, dev_logs_view, dev_anomalias_view,
    dev_auditoria_api_view, dev_auditoria_export_view, dev_logs_download_view,
    # Nuevas herramientas de Base de Datos
    dev_db_status_view, dev_db_optimize_view, dev_db_close_connections_view,
    enviar_notificacion_dev_view,
)

urlpatterns = [
    # ─── Autenticación ────────────────────────────────────────────────────────
    path('login/', login_view, name='login'),
    path('logout/', custom_logout_view, name='logout'),

    # ─── Dashboard ────────────────────────────────────────────────────────────
    path('', dashboard_view, name='home'),

    # ─── Expedientes ─────────────────────────────────────────────────────────
    path('expedientes/', expedientes_view, name='expedientes'),
    path('expedientes/solventes/', lista_solventes_view, name='lista_solventes'),
    path('expedientes/incompletos/', lista_incompletos_view, name='lista_incompletos'),
    path('expedientes/archivos/', digitalizacion_masiva_view, name='digitalizacion'),
    path('expedientes/nuevo/', nuevo_expediente_view, name='nuevo_expediente'),
    path('expedientes/eliminar-masivo/', eliminar_masivo_expedientes_view, name='eliminar_masivo_expedientes'),
    path('expedientes/<str:cedula>/', detalle_expediente_view, name='detalle_expediente'),
    path('expedientes/editar/<str:cedula>/', editar_expediente_view, name='editar_expediente'),
    path('expedientes/eliminar/<str:cedula>/', eliminar_expediente_view, name='eliminar_expediente'),

    # ─── Calificaciones ───────────────────────────────────────────────────────
    path('calificaciones/', carga_masiva_view, name='calificaciones'),
    path('calificaciones/notas-certificadas/', notas_certificadas_view, name='notas_certificadas'),
    path('calificaciones/notas-certificadas/upload/', notas_certificadas_upload_view, name='notas_certificadas_upload'),
    path('calificaciones/notas-certificadas/download/<int:pk>/', notas_certificadas_download_view, name='notas_certificadas_download'),
    path('calificaciones/notas-certificadas/unificar/', notas_certificadas_unificar_view, name='notas_certificadas_unificar'),
    path('calificaciones/notas-certificadas/delete/', notas_certificadas_delete_view, name='notas_certificadas_delete'),
    path('calificaciones/notas-certificadas/emitir-auto/<str:cedula>/', emitir_notas_certificadas_auto_view, name='emitir_notas_certificadas_auto'),
    path('calificaciones/notas-certificadas/emitir-xlsx/<str:cedula>/', emitir_notas_certificadas_xlsx_view, name='emitir_notas_certificadas_xlsx'),
    path('notas/', notas_calificaciones_view, name='notas_calificaciones'),

    # ─── Docentes (mockup estático — reemplazado por docentes.urls para el portal) ──
    path('docentes/notas/', notas_docentes_view, name='notas_docentes'),

    # ─── Portal Docente ───────────────────────────────────────────────────────
    path('docentes/', include('docentes.urls')),

    # ─── Títulos ──────────────────────────────────────────────────────────────
    path('titulos/', titulos_view, name='titulos'),
    path('titulos/generar/<str:cedula>/', generar_titulo_view, name='generar_titulo'),
    path('expedientes/constancia/<str:cedula>/', generar_constancia_estudio_view, name='constancia_estudio'),
    path('expedientes/emitir/<str:cedula>/<str:tipo_documento>/', emitir_documento_formato_view, name='emitir_documento_formato'),
    path('expedientes/boleta/<str:cedula>/', generar_boleta_view, name='boleta_calificaciones'),

    # ─── Usuarios / Operadores ────────────────────────────────────────────────
    path('usuarios/', usuarios_view, name='usuarios'),
    path('usuarios/nuevo/', crear_operador_view, name='crear_operador'),
    path('usuarios/revocar/<int:user_id>/', revocar_operador_view, name='revocar_operador'),
    path('usuarios/eliminar/<int:user_id>/', eliminar_usuario_view, name='eliminar_usuario'),
    path('usuarios/expediente/<int:usuario_id>/', expediente_usuario_view, name='expediente_usuario'),
    path('usuarios/expediente/<int:usuario_id>/guardar/', guardar_perfil_usuario_view, name='guardar_perfil_usuario'),

    # ─── Panel de Desarrollador — Herramientas ────────────────────────────────
    path('desarrollador/', dev_panel_view, name='dev_panel'),
    path('desarrollador/export-db/', dev_export_db_view, name='dev_export_db'),
    path('desarrollador/restore-db/', dev_restore_db_view, name='dev_restore_db'),
    path('desarrollador/run-sql/', dev_run_sql_view, name='dev_run_sql'),
    path('desarrollador/clear-cache/', dev_clear_cache_view, name='dev_clear_cache'),
    path('desarrollador/purge-audit/', dev_purge_audit_view, name='dev_purge_audit'),
    path('desarrollador/test-error/', dev_test_error_view, name='dev_test_error'),
    path('desarrollador/notificacion/enviar/', enviar_notificacion_dev_view, name='enviar_notificacion_dev'),
    # ─── Panel de Desarrollador — Herramientas de Base de Datos ──────────────
    path('desarrollador/api/db/status/', dev_db_status_view, name='dev_db_status'),

    path('desarrollador/api/db/optimize/', dev_db_optimize_view, name='dev_db_optimize'),
    path('desarrollador/api/db/close-connections/', dev_db_close_connections_view, name='dev_db_close_connections'),
    # ─── Panel de Desarrollador — Observabilidad ──────────────────────────────
    path('desarrollador/api/metricas/', dev_metricas_view, name='dev_metricas'),
    path('desarrollador/api/logs/', dev_logs_view, name='dev_logs'),
    path('desarrollador/api/logs/download/', dev_logs_download_view, name='dev_logs_download'),
    path('desarrollador/api/anomalias/', dev_anomalias_view, name='dev_anomalias'),
    path('desarrollador/api/auditoria/', dev_auditoria_api_view, name='dev_auditoria_api'),
    path('desarrollador/api/auditoria/export/', dev_auditoria_export_view, name='dev_auditoria_export'),

    # ─── Analítica e IA ───────────────────────────────────────────────────────
    path('analitica/riesgos/', ia_riesgos_view, name='ia_riesgos'),
    path('auditoria/', auditoria_view, name='auditoria'),
    path('auditoria/limpiar/', auditoria_limpiar_view, name='auditoria_limpiar'),
    path('notificaciones/centro/', centro_notificaciones_view, name='centro_notificaciones'),
    path('api/asistente/chat/', asistente_chat_view, name='asistente_chat'),

    # ─── APIs ─────────────────────────────────────────────────────────────────
    path('api/buscar/', api_buscar_expedientes, name='api_buscar'),
    path('api/estudiantes/check/', api_check_estudiante, name='api_check_estudiante'),
    path('api/observaciones/<str:cedula>/guardar/', guardar_observacion_view, name='guardar_observacion'),
    path('api/observaciones/<str:cedula>/listar/', listar_observaciones_view, name='listar_observaciones'),
    path('api/observaciones/<str:cedula>/pdf/<int:obs_id>/', pdf_observacion_view, name='pdf_observacion'),
    path('api/observaciones/<str:cedula>/eliminar/<int:obs_id>/', eliminar_observacion_view, name='eliminar_observacion'),
    path('api/observaciones/<str:cedula>/notificar/<int:obs_id>/', notificar_representante_view, name='notificar_representante'),
    path('api/estudiantes/<str:cedula>/subir-foto/', api_subir_foto_estudiante, name='api_subir_foto_estudiante'),
    path('api/calificaciones/<str:cedula>/editar/', api_editar_calificacion_view, name='api_editar_calificacion'),
    path('api/calificaciones/<str:cedula>/eliminar/', api_eliminar_calificaciones_ano_view, name='api_eliminar_calificaciones_ano'),

    # ─── Sub-apps ─────────────────────────────────────────────────────────────
    path('admin/', admin.site.urls),
    path('api-ext/', include('api.urls')),
    path('pagos/', include('pagos.urls')),
    path('horarios/', include('horarios.urls')),
    path('auditoria/', include('auditoria.urls')),
    path('asistencias/', include('asistencias.urls')),
    # ─── Actas ────────────────────────────────────────────────────────────────
    path('actas/consejos-secciones/', actas_consejos_view, name='actas_consejos'),
    path('actas/compromisos/', actas_compromisos_view, name='actas_compromisos'),
    path('actas/inasistencias/', actas_inasistencias_view, name='actas_inasistencias'),
]

from django.views.static import serve
from django.urls import re_path

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

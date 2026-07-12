from django.urls import path
from . import views

urlpatterns = [
    # ─── Notificaciones operativas (campana) ───────────────────────────────────
    path('api/recientes/',          views.api_eventos_recientes,   name='auditoria_api_recientes'),
    path('api/conteo/',             views.api_conteo_no_leidos,    name='auditoria_api_conteo'),
    path('api/marcar-leido/<int:evento_id>/', views.api_marcar_leido, name='auditoria_api_marcar_leido'),
    path('api/marcar-todos/',       views.api_marcar_todos_leidos, name='auditoria_api_marcar_todos'),
    path('api/eliminar/<int:evento_id>/', views.api_eliminar_notificacion, name='auditoria_api_eliminar'),
    path('api/vaciar/',              views.api_vaciar_notificaciones, name='auditoria_api_vaciar'),

    # ─── Sistema de Aprobaciones ───────────────────────────────────────────────
    path('api/solicitudes/crear/',              views.api_crear_solicitud,       name='api_crear_solicitud'),
    path('api/solicitudes/pendientes/',         views.api_solicitudes_pendientes, name='api_solicitudes_pendientes'),
    path('api/solicitudes/historial/',          views.api_historial_solicitudes, name='api_historial_solicitudes'),
    path('api/solicitudes/<int:solicitud_id>/aprobar/',      views.api_aprobar_solicitud,     name='api_aprobar_solicitud'),
    path('api/solicitudes/<int:solicitud_id>/rechazar/',     views.api_rechazar_solicitud,    name='api_rechazar_solicitud'),
    path('api/solicitudes/mis-respuestas/',     views.api_mis_solicitudes,       name='api_mis_solicitudes'),
    path('api/solicitudes/conteo/',             views.api_conteo_solicitudes,    name='api_conteo_solicitudes'),
    path('api/solicitudes/<int:solicitud_id>/marcar-leida/', views.api_marcar_solicitud_leida, name='api_marcar_solicitud_leida'),

    # ─── Vistas de Página ──────────────────────────────────────────────────────
    path('aprobaciones/',            views.aprobaciones_view,          name='aprobaciones'),
    path('notificaciones-personal/', views.notificaciones_personal_view, name='notificaciones_personal'),
]

from django.urls import path
from . import views

urlpatterns = [
    # ─── Portal Docente (solo rol DOCENTE) ────────────────────────────────────
    path('portal/', views.dashboard_docente_view, name='portal_docente'),
    path('calificaciones/', views.calificaciones_docente_view, name='calificaciones_docente'),
    path('planificacion/', views.planificacion_docente_view, name='planificacion_docente'),

    # ─── Gestión Administrativa ───────────────────────────────────────────────
    path('gestion/', views.gestion_docentes_view, name='gestion_docentes'),
    path('gestion/<int:docente_id>/', views.perfil_docente_admin_view, name='perfil_docente_admin'),
    path('periodos/', views.gestion_periodos_view, name='gestion_periodos'),

    # ─── APIs Administrativas ─────────────────────────────────────────────────
    path('api/perfil/guardar/', views.api_guardar_perfil_docente, name='api_guardar_perfil_docente'),
    path('api/asignacion/', views.api_gestionar_asignacion, name='api_gestionar_asignacion'),
    path('api/asignaciones/<int:docente_id>/', views.api_asignaciones_docente, name='api_asignaciones_docente'),
    path('api/materias-disponibles/', views.api_materias_disponibles, name='api_materias_disponibles'),

    # ─── APIs Portal Docente ──────────────────────────────────────────────────
    path('api/secciones/', views.api_secciones_docente, name='api_secciones_docente'),
    path('api/materias/', views.api_materias_docente, name='api_materias_docente'),
    path('api/combinaciones/', views.api_combinaciones_docente, name='api_combinaciones_docente'),
    path('api/materias-combo/', views.api_materias_por_combinacion, name='api_materias_por_combinacion'),
    path('api/estudiantes/', views.api_estudiantes_seccion, name='api_estudiantes_seccion'),
    path('api/buscar-estudiantes-gestion/', views.api_buscar_estudiantes_gestion, name='api_buscar_estudiantes_gestion'),
    path('api/evaluaciones/', views.api_evaluaciones_asignatura, name='api_evaluaciones_asignatura'),
    path('api/evaluacion/crear/', views.api_crear_evaluacion, name='api_crear_evaluacion'),
    path('api/notas/guardar/', views.api_guardar_notas, name='api_guardar_notas'),
    path('api/notas/guardar-individual/', views.api_guardar_nota_estudiante, name='api_guardar_nota_estudiante'),
    path('api/periodo/cerrar/', views.api_cerrar_periodo, name='api_cerrar_periodo'),
    path('api/periodos/', views.api_periodos_list_create, name='api_periodos_list_create'),
    path('api/periodos/<int:pk>/', views.api_periodo_update_delete, name='api_periodo_update_delete'),
    path('api/evaluaciones/eliminar-masivo/', views.api_eliminar_evaluaciones, name='api_eliminar_evaluaciones'),
    path('api/evaluaciones/buscar-admin/', views.api_buscar_evaluaciones_admin, name='api_buscar_evaluaciones_admin'),
    
    # ─── APIs Planificación Docente ───────────────────────────────────────────
    path('api/planificacion/temas/', views.api_listar_temas, name='api_listar_temas'),
    path('api/planificacion/tema/crear/', views.api_crear_tema, name='api_crear_tema'),
    path('api/planificacion/tema/eliminar/', views.api_eliminar_tema, name='api_eliminar_tema'),
    path('api/planificacion/material/subir/', views.api_subir_material, name='api_subir_material'),
    path('api/planificacion/material/eliminar/', views.api_eliminar_material, name='api_eliminar_material'),
    path('api/planificacion/tarea/crear/', views.api_crear_tarea, name='api_crear_tarea'),
    path('api/planificacion/tarea/editar/', views.api_editar_tarea, name='api_editar_tarea'),
    path('api/planificacion/tarea/eliminar/', views.api_eliminar_tarea, name='api_eliminar_tarea'),
    
    # ─── Proxy hacia Flask (Plan de Evaluación) ──────────────────────────────
    path('api/plan-evaluacion/flask/<int:docente_id>/', views.api_plan_evaluacion_flask, name='api_plan_evaluacion_flask'),
]

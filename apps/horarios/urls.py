from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_horarios, name='horarios_dashboard'),
    path('<int:horario_id>/', views.dashboard_horarios, name='horarios_dashboard_id'),
    path('lista/', views.lista_horarios, name='horarios_lista'),
    path('api/obtener/', views.api_obtener_horarios, name='api_obtener_horarios'),
    path('api/guardar/', views.api_guardar_bloque, name='api_guardar_bloque'),
    path('api/eliminar/<int:bloque_id>/', views.api_eliminar_bloque, name='api_eliminar_bloque'),
    path('api/limpiar/<int:horario_id>/', views.api_limpiar_horario, name='api_limpiar_horario'),
    path('api/restablecer/', views.api_restablecer_horarios, name='api_restablecer_horarios'),
    path('api/validar/', views.api_validar_horario, name='api_validar_horario'),
    path('exportar/excel/<int:horario_id>/', views.exportar_excel, name='exportar_horario_excel'),
    path('api/periodos/', views.api_periodos, name='api_periodos'),
    path('api/periodos/crear/', views.api_crear_periodo, name='api_crear_periodo'),
    path('api/asignaciones/', views.api_asignaciones_horario, name='api_asignaciones_horario'),
]

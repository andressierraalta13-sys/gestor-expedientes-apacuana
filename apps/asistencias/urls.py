from django.urls import path
from . import views

urlpatterns = [
    path('personal/', views.asistencias_personal_view, name='asistencias_personal'),
    path('registro/', views.registro_historico_view, name='asistencias_registro'),
    path('registro/<str:fecha>/', views.detalle_registro_view, name='detalle_registro'),
    path('api/marcar/', views.api_marcar_asistencia, name='api_marcar_asistencia'),
]

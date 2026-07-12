from django.contrib import admin
from .models import AsignacionDocente, Evaluacion, NotaEvaluacion, PeriodoCierre

@admin.register(AsignacionDocente)
class AsignacionDocenteAdmin(admin.ModelAdmin):
    list_display = ('docente', 'asignatura', 'ano_grado', 'seccion', 'periodo', 'activa')
    list_filter = ('periodo', 'activa', 'ano_grado')
    search_fields = ('docente__username', 'asignatura__nombre')

@admin.register(Evaluacion)
class EvaluacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'asignatura', 'tipo', 'ponderacion', 'seccion', 'periodo', 'creado_por')
    list_filter = ('tipo', 'periodo', 'asignatura')

@admin.register(NotaEvaluacion)
class NotaEvaluacionAdmin(admin.ModelAdmin):
    list_display = ('inscripcion', 'evaluacion', 'nota', 'es_borrador', 'fecha_registro')
    list_filter = ('es_borrador',)

@admin.register(PeriodoCierre)
class PeriodoCierreAdmin(admin.ModelAdmin):
    list_display = ('asignatura', 'seccion', 'periodo', 'cerrado', 'cerrado_por', 'fecha_cierre')
    list_filter = ('cerrado',)

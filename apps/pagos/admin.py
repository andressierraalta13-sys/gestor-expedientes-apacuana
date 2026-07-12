from django.contrib import admin
from .models import Personal, PeriodoPagoPersonal, PagoPersonal, ConceptoPago, DeudaEstudiante, PagoEstudiante

admin.site.register(Personal)
admin.site.register(PeriodoPagoPersonal)
admin.site.register(PagoPersonal)
admin.site.register(ConceptoPago)
admin.site.register(DeudaEstudiante)
admin.site.register(PagoEstudiante)

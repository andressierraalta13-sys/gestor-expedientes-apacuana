from django.urls import path
from .views import agenda_personal_view, agenda_estudiantes_view, servicios_gastos_view
from .api_views import (
    registrar_pago_estudiante_api, agregar_personal_api, 
    pago_masivo_personal_api, historial_pagos_personal_api, 
    historial_pagos_estudiante_api,
    api_registrar_gasto, api_cambiar_estado_gasto, api_eliminar_gasto
)

urlpatterns = [
    path('personal/', agenda_personal_view, name='pagos_personal'),
    path('estudiantes/', agenda_estudiantes_view, name='pagos_estudiantes'),
    path('servicios/', servicios_gastos_view, name='pagos_servicios'),
    
    path('api/estudiantes/pagar/', registrar_pago_estudiante_api, name='api_pagar_estudiante'),
    path('api/personal/agregar/', agregar_personal_api, name='api_agregar_personal'),
    path('api/personal/pago-masivo/', pago_masivo_personal_api, name='api_pago_masivo'),
    path('api/personal/<int:empleado_id>/historial/', historial_pagos_personal_api, name='api_historial_pagos_personal'),
    path('api/estudiantes/<int:estudiante_id>/historial/', historial_pagos_estudiante_api, name='api_historial_pagos_estudiante'),
    
    path('api/servicios/registrar/', api_registrar_gasto, name='api_registrar_gasto'),
    path('api/servicios/<int:gasto_id>/estado/', api_cambiar_estado_gasto, name='api_cambiar_estado_gasto'),
    path('api/servicios/<int:gasto_id>/eliminar/', api_eliminar_gasto, name='api_eliminar_gasto'),
]

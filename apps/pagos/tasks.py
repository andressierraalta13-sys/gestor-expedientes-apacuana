from celery import shared_task
from .models import Personal, PeriodoPagoPersonal, PagoPersonal
import time

@shared_task(bind=True)
def pagar_nomina_masiva(self, empleados_ids, periodo_id, metodo_pago):
    total = len(empleados_ids)
    periodo = PeriodoPagoPersonal.objects.get(id=periodo_id)
    
    procesados = 0
    for emp_id in empleados_ids:
        persona = Personal.objects.get(id=emp_id)
        PagoPersonal.objects.create(
            personal=persona,
            periodo=periodo,
            monto_pagado=persona.salario_base,
            saldo_pendiente=0,
            metodo_pago=metodo_pago,
            estado='PAGADO'
        )
        procesados += 1
        self.update_state(state='PROGRESS', meta={'current': procesados, 'total': total})
        time.sleep(0.05) 

    return {'status': 'COMPLETADO', 'procesados': procesados}

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from usuarios.decorators import role_required # Importando tu decorador existente
from .models import Personal, DeudaEstudiante

@login_required
@role_required('ADMINISTRATIVO', 'PERSONAL')
def agenda_personal_view(request):
    empleados = Personal.objects.filter(activo=True)
    return render(request, 'pagos/agenda_personal.html', {'empleados': empleados})

from estudiantes.models import Estudiante

@login_required
@role_required('ADMINISTRATIVO', 'PERSONAL')
def agenda_estudiantes_view(request):
    # Mostramos a todos los estudiantes sin depender de si tienen deuda previa
    estudiantes = Estudiante.objects.all().order_by('nombres', 'apellidos')
    return render(request, 'pagos/agenda_estudiantes.html', {'estudiantes': estudiantes})

from django.db.models import Sum, Max, Count
from django.utils import timezone
from .models import GastoServicio, CategoriaServicio

@login_required
@role_required('ADMINISTRATIVO', 'PERSONAL')
def servicios_gastos_view(request):
    hoy = timezone.now()
    
    # Localización de meses a español
    MESES = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
        9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
    }
    mes_actual_esp = f"{MESES[hoy.month]} {hoy.year}"

    # Asegurar categorias básicas
    if not CategoriaServicio.objects.exists():
        CategoriaServicio.objects.create(nombre="Mantenimiento")
        CategoriaServicio.objects.create(nombre="Servicios Públicos")
        CategoriaServicio.objects.create(nombre="Infraestructura")
        CategoriaServicio.objects.create(nombre="Compras")
        CategoriaServicio.objects.create(nombre="Emergencias")

    categorias = CategoriaServicio.objects.filter(es_activa=True)
    
    # Filtros
    qs = GastoServicio.objects.all().select_related('categoria', 'responsable', 'aprobado_por').order_by('-fecha_registro')
    
    # KPI Mes Actual - Acumulador dinámico en tiempo real (todos los gastos del mes)
    gastos_mes = qs.filter(fecha_pago__month=hoy.month, fecha_pago__year=hoy.year)
    total_mes = gastos_mes.aggregate(Sum('equivalente_bs'))['equivalente_bs__sum'] or 0
    gasto_mas_alto = gastos_mes.aggregate(Max('equivalente_bs'))['equivalente_bs__max'] or 0
    
    return render(request, 'pagos/servicios.html', {
        'gastos': qs,
        'categorias': categorias,
        'total_mes': total_mes,
        'gasto_mas_alto': gasto_mas_alto,
        'mes_actual': mes_actual_esp
    })

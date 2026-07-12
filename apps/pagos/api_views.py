from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from api.permissions import CheckRolePermission 
from .models import DeudaEstudiante, PagoEstudiante
from decimal import Decimal

class IsAdministrativo(CheckRolePermission):
    allowed_roles = ['ADMINISTRATIVO', 'PERSONAL']

from estudiantes.models import Estudiante
from .models import ConceptoPago

@api_view(['POST'])
@permission_classes([IsAdministrativo])
def registrar_pago_estudiante_api(request):
    estudiante_id = request.data.get('estudiante_id')
    monto = Decimal(str(request.data.get('monto_pagado', '0')))
    metodo = request.data.get('metodo_pago')
    comprobante = request.data.get('comprobante')
    obs = request.data.get('observaciones', 'Abono Administrativo')

    try:
        estudiante = Estudiante.objects.get(id=estudiante_id)
        
        concepto, _ = ConceptoPago.objects.get_or_create(
            nombre='Abono Libre',
            defaults={
                'monto_base': 0, 'periodicidad': 'Bajo demanda',
                'es_obligatorio': False, 'aplicable_a_grados': 'Todos'
            }
        )

        deuda, _ = DeudaEstudiante.objects.get_or_create(
            estudiante=estudiante,
            concepto=concepto,
            periodo_academico='Actual',
            defaults={'monto_total': 0, 'saldo_pendiente': 0}
        )
        
        # Validar comprobante duplicado si se ingresó
        if comprobante and PagoEstudiante.objects.filter(numero_comprobante=comprobante).exists():
            return Response({'error': 'Ese comprobante ya fue registrado previamente.'}, status=400)

        PagoEstudiante.objects.create(
            deuda=deuda,
            monto_pagado=monto,
            metodo_pago=metodo,
            numero_comprobante=comprobante,
            observaciones=obs,
            usuario_que_registra=request.user
        )
        return Response({'success': 'Pago registrado con éxito referenciado al estudiante.'})
    except Estudiante.DoesNotExist:
        return Response({'error': 'Estudiante no encontrado en la base de datos.'}, status=404)

from datetime import date
from django.db.models import Sum
from .models import Personal, PeriodoPagoPersonal, PagoPersonal
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

@api_view(['POST'])
@permission_classes([IsAdministrativo])
def agregar_personal_api(request):
    data = request.data
    try:
        nuevo = Personal.objects.create(
            nombre_completo=data['nombre_completo'],
            cedula=data['cedula'],
            cargo=data['cargo'],
            fecha_ingreso=data['fecha_ingreso'],
            telefono=data.get('telefono', ''),
            correo=data.get('correo', ''),
            esta_en_gestion_docentes=data.get('esta_en_gestion_docentes', False),
            activo=data.get('activo', True)
        )
        return Response({'success': 'Personal agregado con éxito'})
    except Exception as e:
        return Response({'error': str(e)}, status=400)

@api_view(['POST'])
@permission_classes([IsAdministrativo])
def pago_masivo_personal_api(request):
    """
    Procesa pagos masivos de nómina.
    Siempre retorna JSON estructurado. Registra evento de auditoría al finalizar.
    """
    import logging
    logger = logging.getLogger(__name__)

    pagos_data = request.data.get('pagos', {})
    usuario_str = str(request.user) if request.user else 'Sistema'

    # ── Validación inicial ──────────────────────────────────────────────────
    if not pagos_data:
        return Response({'error': 'No se recibieron datos de pago.'}, status=400)

    try:
        hoy = date.today()
        mes_cadena = hoy.strftime('%B %Y').capitalize()
        periodo, _ = PeriodoPagoPersonal.objects.get_or_create(
            periodo=mes_cadena,
            defaults={'fecha_inicio': hoy.replace(day=1), 'fecha_fin': hoy, 'fecha_limite_pago': hoy}
        )
    except Exception as e:
        logger.error(f"[PagoMasivo] Error creando período: {e}", exc_info=True)
        return Response({'error': f'Error al preparar el período de pago: {str(e)}'}, status=500)

    # ── Procesamiento por empleado ──────────────────────────────────────────
    procesados = []
    errores    = []

    for emp_id, detalles in pagos_data.items():
        try:
            empleado = Personal.objects.get(id=emp_id)
            monto_pagado = Decimal(str(detalles['monto']))

            # Se elimina la lógica de saldo_pendiente basada en salario_base
            saldo_pendiente = Decimal('0')
            estado = 'PAGADO'

            PagoPersonal.objects.create(
                personal=empleado,
                periodo=periodo,
                monto_pagado=monto_pagado,
                saldo_pendiente=saldo_pendiente,
                metodo_pago=detalles['metodo'],
                numero_comprobante=detalles.get('comprobante', ''),
                observaciones=detalles.get('obs', ''),
                estado=estado
            )
            procesados.append({'id': emp_id, 'nombre': empleado.nombre_completo, 'estado': estado})
            logger.info(f"[PagoMasivo] Pago registrado → empleado_id={emp_id} monto={monto_pagado}")

        except Personal.DoesNotExist:
            msg = f"Empleado ID {emp_id} no encontrado en la nómina."
            errores.append({'id': emp_id, 'error': msg})
            logger.warning(f"[PagoMasivo] {msg}")
        except (KeyError, ValueError) as e:
            msg = f"Datos inválidos para empleado ID {emp_id}: {str(e)}"
            errores.append({'id': emp_id, 'error': msg})
            logger.warning(f"[PagoMasivo] {msg}")
        except Exception as e:
            msg = f"Error inesperado para empleado ID {emp_id}: {str(e)}"
            errores.append({'id': emp_id, 'error': msg})
            logger.error(f"[PagoMasivo] {msg}", exc_info=True)

    # ── Registro de auditoría ───────────────────────────────────────────────
    hay_errores = bool(errores)
    try:
        from auditoria.models import EventoAuditoria
        EventoAuditoria.objects.create(
            tipo='PAGO_MASIVO_ERROR' if hay_errores else 'PAGO_MASIVO_OK',
            descripcion=(
                f"Pago masivo de nómina — período '{mes_cadena}'. "
                f"{len(procesados)} procesado(s), {len(errores)} error(es)."
            ),
            modulo='Pagos / Nómina',
            usuario=usuario_str,
            exitoso=not hay_errores,
            detalle_json={
                'periodo': mes_cadena,
                'procesados': procesados,
                'errores': errores,
            }
        )
    except Exception as audit_err:
        logger.warning(f"[PagoMasivo] No se pudo registrar evento de auditoría: {audit_err}")

    # ── Respuesta estructurada ──────────────────────────────────────────────
    if errores and not procesados:
        return Response({
            'error': 'Ningún pago pudo ser procesado.',
            'errores': errores,
        }, status=400)

    if errores:
        return Response({
            'success': f'{len(procesados)} pago(s) procesado(s) con advertencias.',
            'procesados': procesados,
            'errores': errores,
        }, status=207)  # 207 Multi-Status

    return Response({
        'success': f'Pago masivo completado exitosamente. {len(procesados)} registro(s) procesado(s).',
        'procesados': procesados,
    })

from dateutil.relativedelta import relativedelta

@api_view(['GET'])
@permission_classes([IsAdministrativo])
def historial_pagos_personal_api(request, empleado_id):
    try:
        empleado = Personal.objects.get(id=empleado_id)
        
        # Limpieza automática: Eliminar pagos con más de 2 meses de antigüedad
        hace_2_meses = date.today() - relativedelta(months=2)
        PagoPersonal.objects.filter(personal=empleado, fecha_pago__lt=hace_2_meses).delete()
        
        # Obtener historial reciente ordenado del más reciente al más antiguo
        pagos = PagoPersonal.objects.filter(personal=empleado).order_by('-fecha_pago', '-id')
        
        data = []
        for p in pagos:
            data.append({
                'id': p.id,
                'monto': float(p.monto_pagado),
                'metodo': p.get_metodo_pago_display(),
                'comprobante': p.numero_comprobante or 'N/A',
                'fecha': p.fecha_pago.strftime('%d/%m/%Y'),
                'observaciones': p.observaciones or f"Pago de nómina - {p.periodo.periodo}",
                'estado': p.estado
            })
            
        return Response({'historial': data})
    except Personal.DoesNotExist:
        return Response({'error': 'Empleado no encontrado'}, status=404)

@api_view(['GET'])
@permission_classes([IsAdministrativo])
def historial_pagos_estudiante_api(request, estudiante_id):
    try:
        from estudiantes.models import Estudiante
        estudiante = Estudiante.objects.get(id=estudiante_id)
        
        # Limpieza automática: Eliminar pagos con más de 2 meses de antigüedad
        hace_2_meses = date.today() - relativedelta(months=2)
        PagoEstudiante.objects.filter(deuda__estudiante=estudiante, fecha_pago__lt=hace_2_meses).delete()
        
        # Obtener historial reciente ordenado del más reciente al más antiguo
        pagos = PagoEstudiante.objects.filter(deuda__estudiante=estudiante).order_by('-fecha_pago', '-id')
        
        data = []
        for p in pagos:
            data.append({
                'id': p.id,
                'monto': float(p.monto_pagado),
                'metodo': p.get_metodo_pago_display(),
                'comprobante': p.numero_comprobante or 'N/A',
                'fecha': p.fecha_pago.strftime('%d/%m/%Y'),
                'observaciones': p.observaciones or f"Abono: {p.deuda.concepto.nombre}",
                'estado': p.deuda.estado
            })
            
        return Response({'historial': data})
    except Exception as e:
        return Response({'error': 'Estudiante no encontrado: ' + str(e)}, status=404)

from .models import GastoServicio, CategoriaServicio
from auditoria.models import registrar_evento
from datetime import timedelta

@api_view(['POST'])
@permission_classes([IsAdministrativo])
def api_registrar_gasto(request):
    try:
        data = request.data
        monto = Decimal(str(data.get('monto', 0)))
        moneda = data.get('moneda', 'BS')
        tasa_cambio = Decimal(str(data.get('tasa_cambio', 1.0)))
        
        # Inteligencia: Detectar Gasto Elevado (ej. mayor a 100 USD o equivalente)
        umbral_alerta_usd = 100
        monto_en_usd = monto if moneda == 'USD' else (monto / tasa_cambio if moneda == 'BS' and tasa_cambio > 0 else monto)
        if moneda == 'EUR': # Aproximación si es EUR
            monto_en_usd = monto * Decimal('1.08')
            
        is_elevado = monto_en_usd > umbral_alerta_usd

        # Inteligencia: Detectar duplicado (misma categoria, mismo monto, en los ultimos 5 dias)
        fecha_obj = date.fromisoformat(data['fecha_pago'])
        hace_5_dias = fecha_obj - timedelta(days=5)
        posible_duplicado = GastoServicio.objects.filter(
            categoria_id=data['categoria_id'],
            monto=monto,
            moneda=moneda,
            fecha_pago__gte=hace_5_dias,
            fecha_pago__lte=fecha_obj
        ).exists()

        gasto = GastoServicio.objects.create(
            categoria_id=data['categoria_id'],
            razon=data['razon'],
            monto=monto,
            moneda=moneda,
            tasa_cambio=tasa_cambio,
            beneficiario_cedula_rif=data['beneficiario_cedula_rif'],
            metodo_pago=data['metodo_pago'],
            referencia=data.get('referencia', ''),
            fecha_pago=data['fecha_pago'],
            responsable=request.user,
            estado=GastoServicio.EstadoGasto.PENDIENTE
        )

        if 'comprobante' in request.FILES:
            gasto.comprobante = request.FILES['comprobante']
            gasto.save()

        # Auditoría base
        registrar_evento(
            tipo='CREACION',
            descripcion=f"Se registró un gasto por {monto} {moneda} - {gasto.razon}",
            modulo='Servicios',
            usuario=request.user.username,
            nivel_riesgo='MEDIO' if is_elevado else 'INFORMATIVO'
        )

        alertas = []
        if is_elevado:
            registrar_evento('ALERTA', f'Gasto elevado detectado: {monto} {moneda}', 'Servicios', request.user.username, 'ADVERTENCIA')
            alertas.append('Gasto elevado detectado.')
        if posible_duplicado:
            registrar_evento('ALERTA', f'Posible pago recurrente o duplicado: {monto} {moneda} en {gasto.categoria.nombre}', 'Servicios', request.user.username, 'ADVERTENCIA')
            alertas.append('Posible gasto duplicado o recurrente detectado.')

        return Response({'success': 'Gasto registrado correctamente.', 'alertas': alertas})
    except Exception as e:
        return Response({'error': str(e)}, status=400)

@api_view(['POST'])
@permission_classes([IsAdministrativo])
def api_cambiar_estado_gasto(request, gasto_id):
    # Solo roles superiores pueden aprobar/pagar/rechazar
    # Como IsAdministrativo permite PERSONAL, filtramos aquí
    if request.user.rol == 'PERSONAL':
        registrar_evento('BLOQUEO_ACCESO', f'Intento de aprobar gasto ID {gasto_id}', 'Servicios', request.user.username, 'CRITICO')
        return Response({'error': 'No tienes permisos para cambiar el estado de los gastos.'}, status=403)

    try:
        gasto = GastoServicio.objects.get(id=gasto_id)
        nuevo_estado = request.data.get('estado')
        
        if nuevo_estado in dict(GastoServicio.EstadoGasto.choices):
            gasto.estado = nuevo_estado
            if nuevo_estado in ['APROBADO', 'PAGADO', 'RECHAZADO']:
                gasto.aprobado_por = request.user
            gasto.save()
            
            registrar_evento(
                tipo='MODIFICACION',
                descripcion=f"El gasto '{gasto.razon}' cambió a estado {nuevo_estado}.",
                modulo='Servicios',
                usuario=request.user.username,
                nivel_riesgo='MEDIO'
            )
            return Response({'success': 'Estado actualizado.'})
        return Response({'error': 'Estado inválido.'}, status=400)
    except GastoServicio.DoesNotExist:
        return Response({'error': 'Gasto no encontrado.'}, status=404)

@api_view(['POST'])
@permission_classes([IsAdministrativo])
def api_eliminar_gasto(request, gasto_id):
    if request.user.rol == 'PERSONAL':
        registrar_evento('BLOQUEO_DELETE', f'Intento de eliminar gasto ID {gasto_id}', 'Servicios', request.user.username, 'CRITICO')
        return Response({'error': 'No tienes permisos para eliminar.'}, status=403)

    try:
        gasto = GastoServicio.objects.get(id=gasto_id)
        descripcion = gasto.razon
        gasto.delete()
        
        registrar_evento(
            tipo='INACTIVACION',
            descripcion=f"Se eliminó el gasto: {descripcion}",
            modulo='Servicios',
            usuario=request.user.username,
            nivel_riesgo='CRITICO'
        )
        return Response({'success': 'Gasto eliminado.'})
    except GastoServicio.DoesNotExist:
        return Response({'error': 'Gasto no encontrado.'}, status=404)

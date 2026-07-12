from django.db import models
from django.utils.timezone import now
from simple_history.models import HistoricalRecords
from estudiantes.models import Estudiante, SoftDeleteManager, AllObjectsManager
from django.conf import settings

class MetodoPagoChoices(models.TextChoices):
    EFECTIVO = 'EFECTIVO', 'Efectivo'
    TRANSFERENCIA = 'TRANSFERENCIA', 'Transferencia en Bs'
    PAGO_MOVIL = 'PAGO_MOVIL', 'Pago Móvil'
    ZELLE = 'ZELLE', 'Zelle'
    BINANCE = 'BINANCE', 'Binance'
    PAYPAL = 'PAYPAL', 'PayPal'
    DEPOSITO = 'DEPOSITO', 'Depósito Bancario'
    OTRO = 'OTRO', 'Otro'

# ================================
# SUBSISTEMA DE PERSONAL
# ================================
class Personal(models.Model):
    nombre_completo = models.CharField(max_length=255)
    cedula = models.CharField(max_length=20, unique=True)
    cargo = models.CharField(max_length=100)
    telefono = models.CharField(max_length=50, blank=True)
    correo = models.EmailField(blank=True)
    esta_en_gestion_docentes = models.BooleanField(default=False, verbose_name="¿Está en gestión docente?")
    fecha_ingreso = models.DateField()
    activo             = models.BooleanField(default=True, help_text='False = registro inactivado (soft delete).')
    fecha_inactivacion = models.DateTimeField(null=True, blank=True,
                                              help_text='Fecha en que el registro fue inactivado.')
    history = HistoricalRecords()

    # Managers: por defecto solo activos; objects_all incluye inactivos
    objects     = SoftDeleteManager()
    objects_all = AllObjectsManager()

    def __str__(self):
        return f"{self.nombre_completo} ({self.cargo})"

class PeriodoPagoPersonal(models.Model):
    periodo = models.CharField(max_length=50, help_text="Ej. Enero 2025")
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    fecha_limite_pago = models.DateField()

    def __str__(self):
        return self.periodo

class PagoPersonal(models.Model):
    class EstadoPago(models.TextChoices):
        PAGADO = 'PAGADO', 'Pagado'
        PENDIENTE = 'PENDIENTE', 'Pendiente parcial'
        ANULADO = 'ANULADO', 'Anulado'

    personal = models.ForeignKey(Personal, on_delete=models.CASCADE, related_name='pagos')
    periodo = models.ForeignKey(PeriodoPagoPersonal, on_delete=models.CASCADE)
    monto_pagado = models.DecimalField(max_digits=10, decimal_places=2)
    saldo_pendiente = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    metodo_pago = models.CharField(max_length=20, choices=MetodoPagoChoices.choices)
    fecha_pago = models.DateField(auto_now_add=True)
    numero_comprobante = models.CharField(max_length=100, blank=True, null=True)
    observaciones = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=EstadoPago.choices, default=EstadoPago.PAGADO)
    history = HistoricalRecords()

# ================================
# SUBSISTEMA DE ESTUDIANTES
# ================================
class ConceptoPago(models.Model):
    nombre = models.CharField(max_length=200)
    monto_base = models.DecimalField(max_digits=10, decimal_places=2)
    periodicidad = models.CharField(max_length=50, help_text="Ej. Mensual, Anual")
    aplicable_a_grados = models.CharField(max_length=255, help_text="Ej. Todos, 1ro a 3ro")
    es_obligatorio = models.BooleanField(default=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

class DeudaEstudiante(models.Model):
    class EstadoDeuda(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        PARCIAL = 'PARCIAL', 'Abono Parcial'
        PAGADO = 'PAGADO', 'Pagado'

    estudiante = models.ForeignKey(Estudiante, on_delete=models.CASCADE, related_name='deudas')
    concepto = models.ForeignKey(ConceptoPago, on_delete=models.CASCADE)
    periodo_academico = models.CharField(max_length=50)
    monto_total = models.DecimalField(max_digits=10, decimal_places=2)
    monto_pagado_acumulado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    saldo_pendiente = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=20, choices=EstadoDeuda.choices, default=EstadoDeuda.PENDIENTE)
    history = HistoricalRecords()

    def calcular_saldos(self):
        self.saldo_pendiente = self.monto_total - self.monto_pagado_acumulado
        if self.saldo_pendiente <= 0:
            self.estado = self.EstadoDeuda.PAGADO
        elif self.monto_pagado_acumulado > 0:
            self.estado = self.EstadoDeuda.PARCIAL
        else:
            self.estado = self.EstadoDeuda.PENDIENTE
        self.save()

class PagoEstudiante(models.Model):
    deuda = models.ForeignKey(DeudaEstudiante, on_delete=models.CASCADE, related_name='pagos')
    monto_pagado = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.CharField(max_length=20, choices=MetodoPagoChoices.choices)
    fecha_pago = models.DateField(auto_now_add=True)
    numero_comprobante = models.CharField(max_length=100, blank=True, null=True, unique=True)
    observaciones = models.TextField(blank=True)
    usuario_que_registra = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        # Al guardar el pago, actualizamos automáticamente la deuda
        super().save(*args, **kwargs)
        self.deuda.monto_pagado_acumulado += self.monto_pagado
        self.deuda.calcular_saldos()

# ================================
# SUBSISTEMA DE SERVICIOS Y GASTOS
# ================================

class CategoriaServicio(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    es_activa = models.BooleanField(default=True)
    
    def __str__(self):
        return self.nombre

class GastoServicio(models.Model):
    class EstadoGasto(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        APROBADO = 'APROBADO', 'Aprobado'
        PAGADO = 'PAGADO', 'Pagado'
        RECHAZADO = 'RECHAZADO', 'Rechazado'

    class MonedaChoices(models.TextChoices):
        BS = 'BS', 'Bolívares (Bs)'
        USD = 'USD', 'Dólares ($)'
        EUR = 'EUR', 'Euros (€)'

    categoria = models.ForeignKey(CategoriaServicio, on_delete=models.RESTRICT, related_name='gastos')
    razon = models.CharField(max_length=255, help_text="Descripción clara del gasto (Ej. Reparación de aire)")
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    moneda = models.CharField(max_length=3, choices=MonedaChoices.choices, default=MonedaChoices.BS)
    tasa_cambio = models.DecimalField(max_digits=12, decimal_places=2, help_text="Tasa BCV del día usada para cálculo", default=1.0)
    equivalente_bs = models.DecimalField(max_digits=14, decimal_places=2, help_text="Total estandarizado a Bs", default=0.0)
    
    beneficiario_cedula_rif = models.CharField(max_length=50)
    metodo_pago = models.CharField(max_length=20, choices=MetodoPagoChoices.choices)
    referencia = models.CharField(max_length=100, blank=True)
    
    fecha_pago = models.DateField()
    comprobante = models.FileField(upload_to='comprobantes_servicios/', blank=True, null=True)
    
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='gastos_registrados')
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='gastos_aprobados')
    
    estado = models.CharField(max_length=20, choices=EstadoGasto.choices, default=EstadoGasto.PENDIENTE)
    
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.razon} - {self.monto} {self.moneda} ({self.estado})"

    def save(self, *args, **kwargs):
        # Asegurar cálculo correcto del equivalente en Bs
        if self.moneda != self.MonedaChoices.BS:
            self.equivalente_bs = float(self.monto) * float(self.tasa_cambio)
        else:
            self.equivalente_bs = self.monto
            self.tasa_cambio = 1.0
        super().save(*args, **kwargs)

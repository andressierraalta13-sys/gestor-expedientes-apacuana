from django.test import TestCase
from estudiantes.models import Estudiante, Expediente
from ia_analitica.asistente_view import _ctx_expedientes

class AsistenteContextTest(TestCase):
    def setUp(self):
        # Crear estudiantes activos (Grados 1 al 5) y sus expedientes
        for i in range(1, 6):
            estudiante = Estudiante.objects.create(
                cedula_identidad=f"1000000{i}",
                nombres=f"Estudiante{i}",
                apellidos="Activo",
                fecha_nacimiento="2010-01-01",
                ano_cursando=i,
                activo=True
            )
            Expediente.objects.create(estudiante=estudiante, estatus='INCOMPLETO')
            
        # Crear estudiantes egresados (Grado 6) y sus expedientes
        for i in range(1, 4):
            egresado = Estudiante.objects.create(
                cedula_identidad=f"2000000{i}",
                nombres=f"Egresado{i}",
                apellidos="Graduado",
                fecha_nacimiento="2008-01-01",
                ano_cursando=6,
                activo=True
            )
            Expediente.objects.create(estudiante=egresado, estatus='SOLVENTE')

    def test_conteo_estudiantes_activos_excluye_egresados(self):
        """Verifica que el conteo total de expedientes en el contexto de la IA coincida con el total de expedientes creados (8)."""
        ctx = _ctx_expedientes()
        
        # Deben haber 8 expedientes en total (5 incompletos + 3 solventes de egresados)
        self.assertEqual(ctx['total'], 8)
        
        # El conteo de egresados en la distribución debe ser 3
        self.assertEqual(ctx['distribucion'].get('Egresados'), 3)

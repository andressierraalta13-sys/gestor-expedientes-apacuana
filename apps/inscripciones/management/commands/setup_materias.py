from django.core.management.base import BaseCommand
from django.db import transaction
from inscripciones.models import Asignatura
from calificaciones.models import Calificacion

class Command(BaseCommand):
    help = 'Elimina todas las materias actuales y registra el listado oficial de 10 materias para 1er a 5to año.'

    def handle(self, *args, **options):
        materias_config = [
            {"nombre": "BIOLOGIA, AMBIENTE Y TECNOLOGIA", "abrv": "BAT"},
            {"nombre": "EDUCACIÓN FÍSICA", "abrv": "EDF"},
            {"nombre": "FÍSICA", "abrv": "FIS"},
            {"nombre": "GEOGRAFÍA, HISTORIA , Y SOBERANÍA NACIONAL", "abrv": "GHC"},
            {"nombre": "IDIOMAS", "abrv": "IDI"},
            {"nombre": "INNOVACIÓN TECNOLÓGICA Y PRODUCTIVA", "abrv": "INP"},
            {"nombre": "LENGUA Y LITERATURA", "abrv": "LYL"},
            {"nombre": "MATEMÁTICA", "abrv": "MAT"},
            {"nombre": "ORIENTACIÓN VOCACIONAL", "abrv": "ORV"},
            {"nombre": "QUÍMICA", "abrv": "QUI"},
        ]

        self.stdout.write("Iniciando restablecimiento de materias...")

        with transaction.atomic():
            # 1. Eliminar calificaciones existentes (para evitar restricción PROTECT)
            # También eliminamos el historial de calificaciones para limpieza total
            calif_deleted, _ = Calificacion.objects.all().delete()
            hist_deleted = 0
            try:
                hist_deleted, _ = Calificacion.history.all().delete()
            except Exception:
                pass

            self.stdout.write(f"- Eliminadas {calif_deleted} calificaciones y {hist_deleted} registros históricos.")

            # 2. Eliminar todas las asignaturas
            asig_deleted, _ = Asignatura.objects.all().delete()
            self.stdout.write(f"- Eliminadas {asig_deleted} asignaturas previas de la base de datos.")

            # 3. Crear las nuevas asignaturas para todos los años del 1 al 5
            creadas = 0
            for ano in range(1, 6):
                for mat in materias_config:
                    codigo = f"A{ano}-{mat['abrv']}"
                    Asignatura.objects.create(
                        codigo=codigo,
                        nombre=mat['nombre'],
                        ano_grado=ano
                    )
                    creadas += 1

            self.stdout.write(self.style.SUCCESS(f"¡Éxito! Se han creado {creadas} nuevas asignaturas (10 materias para años 1 al 5)."))

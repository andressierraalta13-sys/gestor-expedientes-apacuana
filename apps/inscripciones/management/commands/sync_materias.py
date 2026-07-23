from django.core.management.base import BaseCommand
from django.db import transaction
from inscripciones.models import Asignatura

MATERIAS_OFICIALES = [
    {"nombre": "LENGUA Y LITERATURA",           "abrv": "LYL"},
    {"nombre": "IDIOMAS",                       "abrv": "IDI"},
    {"nombre": "MATEMÁTICA",                   "abrv": "MAT"},
    {"nombre": "EDUCACIÓN FÍSICA",              "abrv": "EDF"},
    {"nombre": "BIOLOGÍA, AMBIENTE Y TECNOLOGÍA", "abrv": "BAT"},
    {"nombre": "FÍSICA",                        "abrv": "FIS"},
    {"nombre": "QUÍMICA",                       "abrv": "QUI"},
    {"nombre": "GEOGRAFÍA, HISTORIA Y SOBERANÍA NACIONAL", "abrv": "GHC"},
    {"nombre": "INNOVACIÓN TECNOLÓGICA Y PRODUCTIVA", "abrv": "INP"},
    {"nombre": "ORIENTACIÓN VOCACIONAL",        "abrv": "ORV"},
]

CODIGOS_OFICIALES = {f"A{ano}-{m['abrv']}" for ano in range(1, 6) for m in MATERIAS_OFICIALES}


class Command(BaseCommand):
    help = (
        'Sincroniza las materias oficiales (10 por año, 1er a 5to) sin borrar '
        'calificaciones ni datos existentes. Agrega las que faltan, actualiza '
        'nombres y elimina solo las que no estén en el listado oficial.'
    )

    def handle(self, *args, **options):
        self.stdout.write("Sincronizando materias oficiales...")

        with transaction.atomic():
            existentes = {a.codigo: a for a in Asignatura.objects.all()}
            creadas = 0
            actualizadas = 0
            eliminadas = 0

            # 1. Crear o actualizar las materias del listado oficial
            for ano in range(1, 6):
                for mat in MATERIAS_OFICIALES:
                    codigo = f"A{ano}-{mat['abrv']}"
                    if codigo in existentes:
                        asig = existentes[codigo]
                        if asig.nombre != mat['nombre'] or asig.ano_grado != ano:
                            asig.nombre = mat['nombre']
                            asig.ano_grado = ano
                            asig.save()
                            actualizadas += 1
                    else:
                        Asignatura.objects.create(
                            codigo=codigo,
                            nombre=mat['nombre'],
                            ano_grado=ano,
                        )
                        creadas += 1

            # 2. Eliminar materias que no están en el listado oficial
            # Solo eliminar si NO tienen calificaciones asociadas
            for codigo, asig in existentes.items():
                if codigo not in CODIGOS_OFICIALES:
                    try:
                        asig.delete()
                        eliminadas += 1
                        self.stdout.write(f"  - Eliminada: {codigo}")
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  ! No se pudo eliminar {codigo} (tiene datos asociados): {e}"
                            )
                        )

        self.stdout.write(
            self.style.SUCCESS(
                f"¡Sync completado! Creadas: {creadas}, Actualizadas: {actualizadas}, "
                f"Eliminadas: {eliminadas}"
            )
        )

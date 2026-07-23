from django.db import migrations


def purge_inactivos(apps, schema_editor):
    Estudiante = apps.get_model('estudiantes', 'Estudiante')
    # Borrado físico definitivo de cualquier estudiante inactivo legado (soft-deleted)
    try:
        Estudiante.objects.filter(activo=False).delete()
    except Exception:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ('estudiantes', '0018_alter_estudiante_ano_cursando_and_more'),
    ]

    operations = [
        migrations.RunPython(purge_inactivos, reverse_code=migrations.RunPython.noop),
    ]

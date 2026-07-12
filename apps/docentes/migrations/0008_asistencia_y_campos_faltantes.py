"""
Añade:
- Campo `activo` a TemaClase, MaterialApoyo
- Campo `activa` a TareaDocente  
- Campo `subido_por` a MaterialApoyo
- Campo `creada_por` a TareaDocente
- Modelo RegistroAsistencia (nuevo módulo de asistencia)
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('docentes', '0007_asignaciondocente_aula'),
        ('inscripciones', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Campos activo/activa faltantes ──
        migrations.AddField(
            model_name='temaclase',
            name='activo',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='materialapoyo',
            name='activo',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='tareadocente',
            name='activa',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='materialapoyo',
            name='subido_por',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='materiales_subidos',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='tareadocente',
            name='creada_por',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tareas_creadas',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # ── Nuevo modelo: RegistroAsistencia ──
        migrations.CreateModel(
            name='RegistroAsistencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateField(verbose_name='Fecha de la clase')),
                ('estado', models.CharField(
                    choices=[
                        ('PRESENTE', 'Presente'),
                        ('AUSENTE', 'Ausente'),
                        ('RETARDO', 'Retardo'),
                        ('JUSTIFICADO', 'Justificado'),
                    ],
                    default='PRESENTE',
                    max_length=15,
                )),
                ('observacion', models.TextField(blank=True, default='', max_length=500)),
                ('metodo', models.CharField(
                    choices=[
                        ('MANUAL', 'Manual'),
                        ('QR', 'Código QR'),
                        ('GPS', 'Geolocalización'),
                    ],
                    default='MANUAL',
                    max_length=10,
                )),
                ('hora_registro', models.DateTimeField(auto_now_add=True)),
                ('hora_llegada', models.TimeField(blank=True, null=True, verbose_name='Hora de llegada')),
                ('estudiante', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='asistencias_docente',
                    to='estudiantes.estudiante',
                )),
                ('asignatura', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='asistencias_docente',
                    to='inscripciones.asignatura',
                )),
                ('periodo', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='asistencias_docente',
                    to='inscripciones.periodoacademico',
                )),
                ('seccion', models.CharField(default='U', max_length=5)),
                ('registrado_por', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='asistencias_docente_registradas',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Registro de Asistencia',
                'verbose_name_plural': 'Registros de Asistencia',
                'ordering': ['-fecha', 'estudiante'],
                'unique_together': {('estudiante', 'asignatura', 'periodo', 'seccion', 'fecha')},
            },
        ),
    ]

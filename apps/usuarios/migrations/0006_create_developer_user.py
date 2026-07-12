from django.db import migrations

def create_developer_user(apps, schema_editor):
    Usuario = apps.get_model('usuarios', 'Usuario')
    # Check if admin user exists
    user, created = Usuario.objects.get_or_create(username='admin')
    user.email = 'andressierraalta13@gmail.com'
    user.nombre_completo = 'Desarrollador'
    user.rol = 'DESARROLLADOR'
    user.is_superuser = True
    user.is_staff = True
    user.is_active = True
    
    # Check if password needs to be set (either new or force setting it to admin)
    from django.contrib.auth.hashers import make_password
    # Since set_password is not available on historical models, we use make_password
    if created or not user.password or not user.password.startswith('pbkdf2_'):
        user.password = make_password('admin')
    user.save()

def reverse_developer_user(apps, schema_editor):
    Usuario = apps.get_model('usuarios', 'Usuario')
    Usuario.objects.filter(username='admin').delete()

class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0005_alter_historicalusuario_rol_alter_usuario_rol'),
    ]

    operations = [
        migrations.RunPython(create_developer_user, reverse_developer_user),
    ]

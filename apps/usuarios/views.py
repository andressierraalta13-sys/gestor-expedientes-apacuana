import logging
import requests
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

def login_view(request):
    """Página de inicio de sesión integrada con Supabase Auth."""
    if request.user.is_authenticated:
        return _redirigir_por_rol(request.user)

    error = None
    if request.method == 'POST':
        # El frontend actualmente envía 'username', lo usaremos como email
        email = request.POST.get('username', '').strip() 
        password = request.POST.get('password', '').replace(' ', '')
        
        if not email or not password:
            error = 'Completa todos los campos antes de continuar.'
        else:
            from django.core.cache import cache
            # Check maintenance mode early
            developer_emails = [
                'andressierraalta13@gmail.com',
                'yendersonuribe@gmail.com',
                'abrahamgarcialozano@gmail.com',
                'ghostgaps2006@gmail.com',
                'San1076hm@gmail.com',
                'pachecobrayan521@gmail.com',
                'campozczk@gmail.com'
            ]
            developer_emails_lower = [d.lower() for d in developer_emails]
            email_lower = email.lower()
            if cache.get('maintenance_mode', False) and email_lower not in developer_emails_lower:
                error = 'El sistema se encuentra en mantenimiento programado. Intente más tarde.'
            else:
                if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
                    # Local development authentication fallback (when Supabase is not configured)
                    User = get_user_model()
                    username_part = email_lower.split('@')[0]
                    user_obj = User.objects.filter(email__iexact=email_lower).first()
                    if not user_obj:
                        user_obj = User.objects.filter(username__iexact=username_part).first()
                    
                    if not user_obj:
                        # Auto-create user for testing in local environment
                        rol_asignado = 'DOCENTE' if 'docente' in email_lower else 'PERSONAL'
                        user_obj = User.objects.create_user(
                            username=username_part,
                            email=email_lower if '@' in email_lower else f"{username_part}@gmail.com",
                            password=password,
                            rol=rol_asignado
                        )
                        if rol_asignado == 'DOCENTE':
                            from docentes.models import PerfilDocente, AsignacionDocente
                            from inscripciones.models import PeriodoAcademico, Asignatura
                            PerfilDocente.objects.get_or_create(
                                usuario=user_obj,
                                defaults={
                                    'cedula': f'12345{user_obj.id}',
                                    'nombre': 'Docente',
                                    'apellidos': 'Prueba',
                                    'email': user_obj.email
                                }
                            )
                            periodo = PeriodoAcademico.objects.first()
                            materia = Asignatura.objects.first()
                            if periodo and materia:
                                AsignacionDocente.objects.get_or_create(
                                    docente=user_obj,
                                    asignatura=materia,
                                    periodo=periodo,
                                    ano_grado=materia.ano_grado,
                                    seccion='A',
                                    defaults={'activa': True}
                                )
                    else:
                        # If user exists but password is unusable (created by Supabase), set it
                        if not user_obj.has_usable_password():
                            user_obj.set_password(password)
                            user_obj.save()
                    
                    if user_obj and user_obj.check_password(password):
                        if not user_obj.is_active:
                            error = 'Esta cuenta ha sido desactivada localmente. Contacta al administrador.'
                        else:
                            login(request, user_obj)
                            return _redirigir_por_rol(user_obj)
                    else:
                        error = 'Credenciales incorrectas (desarrollo local).'
                else:
                    # Solicitar token a Supabase Auth (usando REST API para máxima compatibilidad)
                    url = f"{settings.SUPABASE_URL}/auth/v1/token?grant_type=password"
                    headers = {
                        "apikey": settings.SUPABASE_ANON_KEY,
                        "Content-Type": "application/json"
                    }
                    payload = {"email": email, "password": password}
                    
                    try:
                        response = requests.post(url, headers=headers, json=payload, timeout=10)
                        if response.status_code == 200:
                            data = response.json()
                            user_data = data.get('user', {})
                            supabase_email = user_data.get('email', '').strip().lower()
                            
                            # Sincronizar o crear usuario en Django
                            User = get_user_model()
                            
                            # Mapeo fijo de roles según el prompt
                            rol_asignado = 'PERSONAL'
                            if supabase_email in developer_emails_lower:
                                rol_asignado = 'DESARROLLADOR'
                            elif supabase_email == 'whitxblack901@gmail.com':
                                rol_asignado = 'ADMINISTRATIVO' # Directora
                            elif supabase_email == 'andressierraalta12@gmail.com':
                                rol_asignado = 'COORDINADOR' # Administrador
                                
                            # Buscamos por email. Si no existe, lo creamos.
                            # Asignamos el username basado en el email para mantener compatibilidad con otras áreas
                            user_obj = User.objects.filter(email=supabase_email).first()
                            if not user_obj:
                                user_obj = User.objects.filter(username=supabase_email.split('@')[0]).first()
                                if user_obj:
                                    user_obj.email = supabase_email
                                    user_obj.save(update_fields=['email'])
                                else:
                                    user_obj = User.objects.create(
                                        email=supabase_email,
                                        username=supabase_email.split('@')[0],
                                        rol=rol_asignado
                                    )
                            
                            # Forzar actualización de rol solo para los desarrolladores predefinidos
                            if supabase_email in developer_emails_lower:
                                if user_obj.rol != 'DESARROLLADOR':
                                    user_obj.rol = 'DESARROLLADOR'
                                    user_obj.save(update_fields=['rol'])
                            
                            # Asegurar la creación del PerfilAdministrativo local
                            try:
                                from .models import PerfilAdministrativo
                                PerfilAdministrativo.objects.get_or_create(
                                    usuario=user_obj,
                                    defaults={
                                        'nombres': user_obj.username,
                                        'apellidos': '',
                                        'email': user_obj.email,
                                        'telefono': '',
                                        'cargo': user_obj.rol
                                    }
                                )
                            except Exception as e:
                                logger.error(f"Error al asegurar PerfilAdministrativo para {user_obj.username}: {e}", exc_info=True)
                            
                            if not user_obj.is_active:
                                error = 'Esta cuenta ha sido desactivada localmente. Contacta al administrador.'
                            else:
                                login(request, user_obj)
                                
                                try:
                                    from auditoria.models import registrar_evento
                                    registrar_evento(
                                        tipo='LOGIN',
                                        descripcion=f'Inicio de sesión exitoso vía Supabase: {user_obj.email} [{user_obj.rol}]',
                                        modulo='Autenticación',
                                        usuario=user_obj.username,
                                        nivel_riesgo='INFORMATIVO',
                                    )
                                except Exception:
                                    pass
                                return _redirigir_por_rol(user_obj)
                        else:
                            error_data = response.json()
                            error_msg = error_data.get('error_description', 'Credenciales incorrectas o usuario no registrado.')
                            error = f'Error de autenticación: {error_msg}'
                            
                    except requests.exceptions.RequestException as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"Error de conexion con Supabase Auth: {e}", exc_info=True)
                        error = f'Error de conexión con el servicio de autenticación (Supabase): {e}'

    return render(request, 'usuarios/login.html', {'error': error})

def _redirigir_por_rol(user):
    if user.rol == 'DOCENTE':
        return redirect('portal_docente')
    return redirect('home')

def custom_logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def usuarios_view(request):
    if request.user.rol == 'PERSONAL':
        from auditoria.models import registrar_evento
        registrar_evento('ACCESO_DENEGADO', 'Intento de acceso a Gestión de Usuarios', 'Usuarios', request.user.username, 'MEDIO', False)
        return render(request, '403.html', {'mensaje': 'No tienes permisos para ver los usuarios.'}, status=403)
        
    User = get_user_model()
    if request.user.rol == 'DESARROLLADOR':
        usuarios_lista = User.objects.all().order_by('username')
    else:
        usuarios_lista = User.objects.exclude(rol='DESARROLLADOR').order_by('username')
    return render(request, 'usuarios/lista.html', {'usuarios_lista': usuarios_lista})


@login_required
@csrf_exempt
def crear_operador_view(request):
    """Crea un nuevo operador en Supabase y luego localmente."""
    if request.user.rol == 'PERSONAL':
        from auditoria.models import registrar_evento
        registrar_evento('ACCESO_DENEGADO', 'Intento de crear un usuario', 'Usuarios', request.user.username, 'CRITICO', False)
        return JsonResponse({'error': 'No tienes permisos para esta acción.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    User = get_user_model()

    email = request.POST.get('email', '').strip()
    username = request.POST.get('username', '').strip()
    nombre_completo = request.POST.get('nombre_completo', '').strip()
    password = request.POST.get('password', '')
    confirmar = request.POST.get('confirmar_password', '')
    rol = request.POST.get('rol', 'PERSONAL')

    if not email or '@' not in email:
        return JsonResponse({'error': 'Se requiere un correo electrónico válido.'}, status=400)
    if len(password) < 6:
        return JsonResponse({'error': 'La contraseña debe tener al menos 6 caracteres.'}, status=400)
    if password != confirmar:
        return JsonResponse({'error': 'Las contraseñas no coinciden.'}, status=400)
    if User.objects.filter(email=email).exists():
        return JsonResponse({'error': f'El correo "{email}" ya está registrado en la base de datos local.'}, status=400)

    ROLES_VALIDOS = ['DOCENTE', 'ADMINISTRATIVO', 'PERSONAL', 'COORDINADOR', 'DESARROLLADOR']
    if rol == 'DESARROLLADOR' and request.user.rol != 'DESARROLLADOR':
        return JsonResponse({'error': 'No tienes permisos para crear este rol.'}, status=403)
    if rol not in ROLES_VALIDOS:
        rol = 'PERSONAL'

    if not settings.SUPABASE_SERVICE_ROLE_KEY:
        return JsonResponse({
            'error': 'Falta configurar la clave de servicio (service_role) de Supabase. Por favor, añade la variable de entorno SUPABASE_SERVICE_ROLE_KEY en el panel de Vercel.'
        }, status=400)

    # Crear en Supabase Auth usando la API Admin
    url = f"{settings.SUPABASE_URL}/auth/v1/admin/users"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "email": email,
        "password": password,
        "email_confirm": True
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            # Usuario creado en Supabase, ahora crear localmente
            username_local = username if username else email.split('@')[0]
            nuevo = User.objects.create(
                email=email,
                username=username_local,
                nombre_completo=nombre_completo,
                rol=rol,
            )
            # En Django la contraseña no importa porque validamos vía Supabase
            nuevo.set_unusable_password()
            nuevo.save()

            # Forzar creación de PerfilAdministrativo local
            from .models import PerfilAdministrativo
            PerfilAdministrativo.objects.get_or_create(
                usuario=nuevo,
                defaults={
                    'nombres': nombre_completo.split(' ')[0] if nombre_completo else nuevo.username,
                    'apellidos': ' '.join(nombre_completo.split(' ')[1:]) if nombre_completo and len(nombre_completo.split(' ')) > 1 else '',
                    'email': email,
                    'telefono': '',
                    'cargo': rol
                }
            )

            # Sincronizar con el modelo Personal de pagos si existe por correo
            try:
                from pagos.models import Personal
                personal_obj = Personal.objects.filter(correo__iexact=email).first()
                if personal_obj:
                    personal_obj.nombre_completo = nombre_completo or personal_obj.nombre_completo
                    personal_obj.cargo = rol
                    personal_obj.save()
            except Exception as e:
                logger.error(f"Error al sincronizar Personal al crear operador: {e}", exc_info=True)

            # Auditoría
            try:
                from auditoria.models import registrar_evento
                registrar_evento(
                    tipo='CREACION',
                    descripcion=f'Se creó el operador "{email}" con cargo {rol} en Supabase y local.',
                    modulo='Usuarios',
                    usuario=request.user.username,
                    nivel_riesgo='INFORMATIVO',
                    valor_nuevo={'email': email, 'rol': rol}
                )
            except Exception:
                pass

            return JsonResponse({
                'ok': True,
                'usuario': {
                    'id': nuevo.id,
                    'username': nuevo.username,
                    'email': nuevo.email,
                    'nombre_completo': nuevo.nombre_completo,
                    'rol': nuevo.rol,
                }
            })
        else:
            error_data = response.json()
            return JsonResponse({'error': f"Error en Supabase: {error_data.get('message', 'Desconocido')}"}, status=400)
    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': 'Error de comunicación con Supabase Auth.'}, status=500)


@login_required
@csrf_exempt
def revocar_operador_view(request, user_id):
    """Activa o desactiva un operador localmente."""
    if request.user.rol == 'PERSONAL':
        from auditoria.models import registrar_evento
        registrar_evento('ACCESO_DENEGADO', 'Intento de modificar estado de un usuario', 'Usuarios', request.user.username, 'CRITICO', False)
        return JsonResponse({'error': 'No tienes permisos para esta acción.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    User = get_user_model()
    try:
        target = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'Usuario no encontrado.'}, status=404)

    if target == request.user:
        return JsonResponse({'error': 'No puedes modificar tu propia cuenta.'}, status=403)

    if target.rol == 'DESARROLLADOR' and request.user.rol != 'DESARROLLADOR':
        return JsonResponse({'error': 'No tienes permisos para modificar este usuario.'}, status=403)

    target.is_active = not target.is_active
    target.save()

    estado = 'activado' if target.is_active else 'desactivado'
    
    try:
        from auditoria.models import registrar_evento
        registrar_evento(
            tipo='MODIFICACION' if target.is_active else 'INACTIVACION',
            descripcion=f'Operador "{target.email}" fue {estado}.',
            modulo='Usuarios',
            usuario=request.user.username,
            nivel_riesgo='MEDIO' if not target.is_active else 'INFORMATIVO',
            valor_nuevo={'is_active': target.is_active}
        )
    except Exception:
        pass

    return JsonResponse({'ok': True, 'activo': target.is_active, 'mensaje': f'Operador {estado}.'})


@login_required
@csrf_exempt
def eliminar_usuario_view(request, user_id):
    """Elimina permanentemente un usuario de Supabase Auth y de Django."""
    if request.user.rol not in ['ADMINISTRATIVO', 'DESARROLLADOR', 'COORDINADOR']:
        from auditoria.models import registrar_evento
        registrar_evento('ACCESO_DENEGADO', 'Intento de eliminación de usuario sin privilegios', 'Usuarios', request.user.username, 'CRITICO', False)
        return JsonResponse({'error': 'No tienes permisos para esta acción.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    User = get_user_model()
    try:
        target = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'Usuario no encontrado.'}, status=404)

    if target == request.user:
        return JsonResponse({'error': 'No puedes borrar tu propio usuario director en funcionamiento.'}, status=403)

    if target.rol == 'ADMINISTRATIVO' and request.user.rol == 'ADMINISTRATIVO':
        return JsonResponse({'error': 'Un usuario Director no puede eliminar a otro usuario Director.'}, status=403)

    if target.rol == 'DESARROLLADOR' and request.user.rol != 'DESARROLLADOR':
        return JsonResponse({'error': 'No tienes permisos para eliminar a este usuario.'}, status=403)

    email_eliminado = target.email
    rol_eliminado = target.rol
    
    # 1. Eliminar de Supabase Auth
    # Para eliminar de Supabase Auth mediante Admin API, normalmente necesitamos el UUID.
    # Dado que no guardamos el UUID en la base local (podríamos, pero requeriría una migración),
    # haremos una llamada para listar usuarios por correo, obtener el UUID y borrarlo.
    
    if not settings.SUPABASE_SERVICE_ROLE_KEY:
        logger.warning("No se pudo eliminar de Supabase porque SUPABASE_SERVICE_ROLE_KEY no está configurada. Procediendo a eliminar solo localmente.")
    else:
        url_list = f"{settings.SUPABASE_URL}/auth/v1/admin/users"
        headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json"
        }
        
        try:
            # Obtenemos los usuarios y filtramos
            response = requests.get(url_list, headers=headers)
            if response.status_code == 200:
                users_data = response.json().get('users', [])
                user_uuid = None
                for u in users_data:
                    if u.get('email') == email_eliminado:
                        user_uuid = u.get('id')
                        break
            
            if user_uuid:
                # Procedemos a eliminarlo de Supabase
                url_del = f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_uuid}"
                del_response = requests.delete(url_del, headers=headers)
                if del_response.status_code not in [200, 204]:
                    logger.error(f"Fallo al eliminar de Supabase: {del_response.text}")
        except Exception as e:
            pass # Si falla Supabase, igual procedemos a borrarlo localmente por seguridad
        
    # 2. Hard delete local
    try:
        target.delete()
    except Exception as e:
        logger.error(f"Error al eliminar usuario {email_eliminado} de la base de datos: {e}", exc_info=True)
        return JsonResponse({'error': f'Error al eliminar de la base de datos: {str(e)}'}, status=500)

    try:
        from auditoria.models import registrar_evento
        registrar_evento(
            tipo='OTRO',
            descripcion=f'Operador "{email_eliminado}" ({rol_eliminado}) fue ELIMINADO permanentemente de Supabase y Django.',
            modulo='Usuarios',
            usuario=request.user.username,
            nivel_riesgo='CRITICO',
            impacto=f'El usuario ya no puede iniciar sesión. Se liberaron sus registros dependientes.',
            valor_anterior={'email': email_eliminado, 'rol': rol_eliminado}
        )
    except Exception:
        pass

    return JsonResponse({'ok': True, 'mensaje': f'Usuario "{email_eliminado}" eliminado exitosamente.'})


@login_required
def expediente_usuario_view(request, usuario_id):
    from django.shortcuts import get_object_or_404
    from .models import PerfilAdministrativo
    
    User = get_user_model()
    usuario = get_object_or_404(User, id=usuario_id)
    if usuario.rol == 'DESARROLLADOR' and request.user.rol != 'DESARROLLADOR':
        return render(request, '403.html', {'mensaje': 'No tienes permisos para ver este perfil.'}, status=403)
        
    perfil, created = PerfilAdministrativo.objects.get_or_create(usuario=usuario)
    
    context = {
        'usuario': usuario,
        'perfil': perfil,
    }
    return render(request, 'usuarios/expediente_usuario.html', context)


@login_required
def guardar_perfil_usuario_view(request, usuario_id):
    """Guarda los datos del PerfilAdministrativo y sincroniza nombre_completo en el usuario."""
    import json
    from django.shortcuts import get_object_or_404
    from .models import PerfilAdministrativo
    
    User = get_user_model()

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido.'}, status=405)

    usuario = get_object_or_404(User, id=usuario_id)
    if usuario.rol == 'DESARROLLADOR' and request.user.rol != 'DESARROLLADOR':
        return JsonResponse({'ok': False, 'error': 'No tienes permisos para modificar este perfil.'}, status=403)
        
    data = json.loads(request.body)

    # Permitir la edición de username si el rol del usuario actual es ADMINISTRATIVO o DESARROLLADOR
    nuevo_username = data.get('username', '').strip().lower()
    if nuevo_username and (request.user.rol in ['ADMINISTRATIVO', 'DESARROLLADOR', 'COORDINADOR']):
        if nuevo_username != usuario.username:
            if User.objects.filter(username=nuevo_username).exclude(id=usuario.id).exists():
                return JsonResponse({'ok': False, 'error': f'El nombre de usuario "{nuevo_username}" ya está registrado por otro operador.'})
            usuario.username = nuevo_username
            usuario._skip_history = True
            usuario.save(update_fields=['username'])

    # Permitir la edición del rol en el sistema si el rol del usuario actual es ADMINISTRATIVO o DESARROLLADOR
    nuevo_rol = data.get('rol', '').strip()
    if nuevo_rol and (request.user.rol in ['ADMINISTRATIVO', 'DESARROLLADOR', 'COORDINADOR']):
        roles_permitidos = ['PERSONAL', 'ADMINISTRATIVO', 'COORDINADOR', 'DOCENTE']
        if request.user.rol == 'DESARROLLADOR':
            roles_permitidos.append('DESARROLLADOR')
            
        if nuevo_rol in roles_permitidos:
            if not (usuario.rol == 'DESARROLLADOR' and request.user.rol != 'DESARROLLADOR'):
                usuario.rol = nuevo_rol
                usuario._skip_history = True
                usuario.save(update_fields=['rol'])

    perfil, _ = PerfilAdministrativo.objects.get_or_create(usuario=usuario)
    perfil.nombres = data.get('nombres', '').strip()
    perfil.apellidos = data.get('apellidos', '').strip()
    cedula = data.get('cedula', '').strip()
    perfil.cedula = cedula if cedula else None
    perfil.cargo = data.get('cargo', '').strip()
    perfil.telefono = data.get('telefono', '').strip()
    
    # El email de perfil se mantiene pero no cambia el de Supabase
    perfil.email = data.get('email', '').strip() 
    perfil.save()

    # Sincronizar con PerfilDocente si el rol es DOCENTE
    if usuario.rol == 'DOCENTE':
        try:
            from docentes.models import PerfilDocente
            perfil_doc, _ = PerfilDocente.objects.get_or_create(usuario=usuario)
            perfil_doc.nombre = perfil.nombres
            perfil_doc.apellidos = perfil.apellidos
            perfil_doc.cedula = perfil.cedula
            perfil_doc.email = perfil.email
            perfil_doc.telefono = perfil.telefono
            perfil_doc.save()
        except Exception as e:
            logger.error(f"Error al sincronizar PerfilDocente para {usuario.username}: {e}", exc_info=True)

    # Sincronizar con el modelo Personal de pagos si existe por cédula o correo
    try:
        from pagos.models import Personal
        personal_obj = None
        if perfil.cedula:
            personal_obj = Personal.objects.filter(cedula=perfil.cedula).first()
        if not personal_obj and perfil.email:
            personal_obj = Personal.objects.filter(correo__iexact=perfil.email).first()
            
        if personal_obj:
            personal_obj.nombre_completo = f"{perfil.nombres} {perfil.apellidos}".strip() or personal_obj.nombre_completo
            personal_obj.telefono = perfil.telefono or personal_obj.telefono
            personal_obj.correo = perfil.email or personal_obj.correo
            if perfil.cargo:
                personal_obj.cargo = perfil.cargo
            elif usuario.rol:
                personal_obj.cargo = usuario.get_rol_display()
            personal_obj.save()
    except Exception as e:
        logger.error(f"Error al sincronizar Personal para {usuario.username}: {e}", exc_info=True)

    nombre_completo = f"{perfil.nombres} {perfil.apellidos}".strip()
    if nombre_completo:
        usuario.nombre_completo = nombre_completo
        usuario._skip_history = True
        usuario.save(update_fields=['nombre_completo'])

    return JsonResponse({'ok': True})

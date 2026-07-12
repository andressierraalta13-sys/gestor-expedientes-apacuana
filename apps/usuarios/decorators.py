from django.core.exceptions import PermissionDenied
from functools import wraps

def role_required(*allowed_roles):
    """
    Decorador para proteger vistas. El PERSONAL siempre tiene acceso.
    Uso: @role_required(Usuario.Role.COORDINADOR, Usuario.Role.DOCENTE)
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_authenticated:
                if request.user.rol in allowed_roles or request.user.rol == 'PERSONAL' or request.user.rol == 'DESARROLLADOR':
                    return view_func(request, *args, **kwargs)
            raise PermissionDenied("No tienes permisos suficientes.")
        return _wrapped_view
    return decorator

from rest_framework import permissions

class CheckRolePermission(permissions.BasePermission):
    """
    Permiso personalizado para DRF. Verifica si el usuario tiene un rol permitido.
    """
    allowed_roles = []

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.rol in ['PERSONAL', 'DESARROLLADOR']:
            return True
        return request.user.rol in self.allowed_roles

class IsCoordinador(CheckRolePermission):
    allowed_roles = ['COORDINADOR']

class IsDocenteOrCoordinador(CheckRolePermission):
    allowed_roles = ['DOCENTE', 'COORDINADOR']


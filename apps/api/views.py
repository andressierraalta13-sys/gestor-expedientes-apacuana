from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from estudiantes.models import Estudiante
from .serializers import EstudianteSerializer
from .permissions import IsDocenteOrCoordinador
from drf_spectacular.utils import extend_schema, extend_schema_view

@extend_schema_view(
    list=extend_schema(description="Retorna una lista de estudiantes paginada."),
    retrieve=extend_schema(description="Obtiene los detalles de un estudiante específico.")
)
class EstudianteViewSet(viewsets.ModelViewSet):
    queryset = Estudiante.objects.all()
    serializer_class = EstudianteSerializer
    permission_classes = [IsAuthenticated, IsDocenteOrCoordinador]

from django.http import JsonResponse
from estudiantes.tasks import procesar_zip_masivo
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def upload_zip_view(request):
    """
    Recibe el archivo, lo guarda y dispara la tarea de Celery.
    """
    if request.method == 'POST' and request.FILES.get('archivo_zip'):
        archivo = request.FILES['archivo_zip']
        # Guardar en temporal
        fs = FileSystemStorage(location='/tmp/')
        filename = fs.save(archivo.name, archivo)
        filepath = fs.path(filename)
        
        # Disparar Celery
        task = procesar_zip_masivo.delay(filepath)
        
        return JsonResponse({"task_id": task.id, "mensaje": "Procesamiento iniciado"}, status=202)
    return JsonResponse({"error": "No se envió ningún archivo"}, status=400)

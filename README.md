# Gestor de Expedientes APACUANA

El **Gestor de Expedientes APACUANA** es un sistema integral de intranet diseñado para administrar, organizar y optimizar los procesos académicos y administrativos de la institución. Desarrollado en Python con el framework Django, el sistema proporciona una plataforma centralizada donde administradores, docentes y personal autorizado pueden gestionar de forma segura toda la información escolar.

## ¿Qué hace el sistema?

El objetivo principal del sistema es digitalizar y automatizar el flujo de información de la institución educativa. Permite llevar un control exhaustivo del ciclo de vida del estudiante (desde la inscripción inicial hasta la graduación), gestionar el personal docente, administrar los pagos y mensualidades, registrar calificaciones y asistencias, y proporcionar herramientas analíticas (incluso con soporte de Inteligencia Artificial) para la toma de decisiones. Todo esto estructurado bajo un entorno seguro y auditable.

---

## Módulos y Funcionalidades del Sistema

El proyecto está construido bajo una arquitectura modular. Cada módulo (aplicación) se encarga de un área específica del flujo de trabajo de la institución:

### 1. Gestión de Usuarios y Accesos (`usuarios`)
Controla el acceso al sistema mediante un sistema de autenticación. Permite crear y gestionar las credenciales de administradores, personal administrativo y docentes, definiendo roles y permisos estrictos para determinar qué puede ver o modificar cada persona dentro del sistema.

### 2. Expedientes de Estudiantes (`estudiantes`)
Es el núcleo central de la información del alumnado. Administra los perfiles completos de los estudiantes y su relación directa con sus **representantes** (padres o tutores legales). Aquí se almacena información personal, médica, de contacto y el historial general necesario para el expediente físico/digital de cada alumno.

### 3. Proceso de Inscripciones (`inscripciones`)
Automatiza y gestiona la matriculación de los estudiantes en los distintos periodos o años escolares. Facilita la asignación de los estudiantes a sus respectivos grados y secciones, validando los requisitos previos para formalizar su entrada a la institución.

### 4. Control de Pagos y Solvencias (`pagos`)
Administra el aspecto financiero de los estudiantes. Lleva el registro de los pagos de inscripciones, mensualidades y aranceles adicionales. Permite generar comprobantes y mantener un control en tiempo real sobre qué estudiantes se encuentran solventes y quiénes presentan morosidad.

### 5. Gestión del Personal Docente (`docentes`)
Administra el perfil profesional del personal académico de la institución. Permite registrar a los profesores, sus especialidades y asignarles la carga académica (qué materias y en qué secciones van a impartir clases durante el periodo lectivo).

### 6. Calificaciones y Rendimiento (`calificaciones`)
Un módulo crítico donde se registran, calculan y publican las notas de los estudiantes. Gestiona los distintos cortes o lapsos evaluativos, calcula promedios y se encarga de estructurar la información necesaria para la emisión de boletines académicos.

### 7. Control de Asistencias (`asistencias`)
Proporciona la interfaz para el pase de lista. Permite a los docentes o coordinadores llevar un registro diario o por materia de la asistencia estudiantil, ayudando a detectar rápidamente patrones de ausentismo o deserción.

### 8. Gestión de Horarios (`horarios`)
Organiza la distribución del tiempo y el espacio en la institución. Facilita la creación de los horarios de clases, emparejando aulas, asignaturas, secciones y docentes para evitar choques de horario y optimizar los recursos físicos del plantel.

### 9. Proceso de Graduación (`graduacion`)
Gestiona los trámites finales para los estudiantes que culminan su ciclo educativo. Centraliza la validación de requisitos de grado (notas, solvencia administrativa, documentación), la emisión de títulos/certificados y la logística del evento de graduación.

### 10. Analítica e Inteligencia Artificial (`ia_analitica`)
Un módulo avanzado diseñado para procesar los datos históricos y actuales del sistema (rendimiento, asistencias, pagos). Utiliza algoritmos analíticos y de IA para generar reportes inteligentes, identificar estudiantes en riesgo y mostrar tendencias que ayuden a la directiva en la toma de decisiones estratégicas.

### 11. Auditoría y Trazabilidad (`auditoria`)
Mantiene un historial detallado (logs) de seguridad sobre todas las acciones sensibles que ocurren en el sistema (ej. modificaciones de notas, eliminación de pagos, cambios de datos de estudiantes). Registra qué usuario realizó la acción, en qué momento y desde dónde, asegurando la transparencia total del sistema.

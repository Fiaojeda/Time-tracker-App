# Time-tracker-App

Aplicación de escritorio para llevar el control de las horas trabajadas por los empleados: fichajes de entrada/salida, pausas y exportación de informes mensuales en Excel.

## Estructura del proyecto

- `main.py` — punto de entrada de la aplicación.
- `ui.py` — interfaz de usuario (PyQt).
- `database.py` — capa de acceso a datos (SQLite).
- `autostart.py` — utilidades para arranque automático al iniciar sesión.
- `admins.txt` — lista de usuarios (OS username) con permisos de administrador (pueden exportar a Excel).
- `Tabla jornadas.sql`, `Tabla pausas.sql` — esquemas SQL de referencia.
- `assets/` — recursos (iconos, imágenes).

## Requisitos

- Python 3.10+
- Dependencias: `PyQt5` (o `PySide6`, según se use en `ui.py`) y `openpyxl` para exportar Excel.

Instala las dependencias con:

```bash
pip install PyQt5 openpyxl
```

## Ejecución

```bash
python main.py
```

## Administradores

Añade el nombre de usuario del sistema operativo (uno por línea) en `admins.txt`. Solo esos usuarios verán los botones de exportar a Excel en la interfaz.

## Base de datos

La aplicación usa un fichero SQLite local llamado `tracker.db`. Este fichero **no** se versiona en el repositorio (ver `.gitignore`): se crea automáticamente en cada máquina al ejecutar la app por primera vez.
